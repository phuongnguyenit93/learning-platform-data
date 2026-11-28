# Key usage count: đếm số lần sử dụng khóa và kiểm soát giới hạn an toàn

## 1. Vì sao khóa chưa hết hạn vẫn có thể phải ngừng Encrypt?

Một dịch vụ Java dùng **AES-256-GCM** để mã hóa thông tin giao dịch. Khóa được quản lý qua KMS và có lịch rotation hằng năm, nên đội phát triển tin rằng không cần biết mỗi khóa đã được sử dụng bao nhiêu lần.

Sau khi mở rộng, hàng chục JVM cùng sử dụng một **DEK** được unwrap từ KMS. Chúng mã hóa hàng triệu bản ghi nhưng KMS chỉ nhận vài nghìn API calls do DEK được cache. Một số pod còn tạo nonce bằng bộ đếm bắt đầu từ 0 sau restart. Dashboard KMS hiển thị usage thấp, trong khi **cùng cặp (key, nonce)** có thể bị dùng lặp lại.

**Key usage count** là phép đo số lượt sử dụng một **khóa hoặc một phiên bản vật liệu khóa** cho **những thao tác được định nghĩa rõ**, trong khoảng thời gian và phạm vi cụ thể. Tùy mục đích, tổ chức cần đếm Encrypt, Decrypt, Sign, Verify, GenerateMac, Wrap/Unwrap, DeriveKey, **lượt cấp phát nonce**, số byte xử lý hoặc lượt gọi API.

Một hệ thống đếm đúng phải trả lời:

1. **Đếm khóa nào?** Key ID, vật liệu thực, version, alias, copy tại nhiều vùng hay derived key?
2. **Đếm việc gì?** Encrypt/Decrypt/Sign/Unwrap, API request, lần thử hay completed operation?
3. **Khi nào tăng?** Trước phép toán (reserve), sau thành công hay khi audit event được ghi?
4. **Phạm vi nào?** JVM, cluster, regions, providers, tenants, tất cả nơi cùng raw material được dùng?
5. **Mục tiêu gì?** Giới hạn thuật toán, rotation, phát hiện misuse, quota hay kiểm toán?
6. **Hết ngân sách thì sao?** Chặn phép mới, đổi key version, giữ legacy Decrypt, điều tra?

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài thuộc chương **Key use** và kết nối vòng đời khóa, mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM, audit và khôi phục.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **usage count, API request count, cryptographic invocation, nonce reservation** và business operation count.
- Gắn bộ đếm với đúng **key material/version, thuật toán, mode, operation và policy**.
- Giải thích vai trò của **nonce uniqueness, usage limits và dữ liệu đã xử lý** với AES-GCM.
- Thiết kế **reserve-before-encrypt** và không tái cấp nonce khi có lỗi không chắc chắn.
- Biết vì sao **AtomicLong trong một JVM** không đồng bộ nhiều pods/regions.
- Tách **KMS KEK Unwrap count** khỏi **DEK local Encrypt count** khi dùng envelope encryption.
- Theo dõi Sign/MAC/Derive/Verify với các ngữ nghĩa khác nhau.
- Tạo metric, audit, cảnh báo và runbook rotation/revocation khi đạt ngưỡng hoặc có sự cố.
- Đọc Java 17 demo giới hạn AES-GCM Encrypt và phát nonce không lặp **trong một JVM**.
- Phân biệt **rewrap KEK, đổi DEK/re-encrypt** và quyền Decrypt dữ liệu lịch sử.

## 2. Định nghĩa counter phải đủ ngữ cảnh

Bản ghi này chưa đủ ý nghĩa:

~~~text
keyId = billing-key
usageCount = 850000
~~~

Chưa biết đó là 850.000 lần Encrypt, Decrypt, retry, API billing request hay cache hit; chưa biết alias đã đổi version hay key có copy sang region khác.

Định nghĩa tốt hơn:

~~~text
KeyUsageMetric =
    key material identity + immutable version / key ID
    + key class + algorithm / mode + purpose
    + operation (ENCRYPT, DECRYPT, SIGN, WRAP, UNWRAP, ...)
    + semantics (RESERVED, ATTEMPTED, COMPLETED, DENIED)
    + scope (all writers / region / provider / cluster)
    + observation time + evidence source + policy version
~~~

### 2.1. Các đơn vị không thể thay nhau

| Bộ đếm | Ghi nhận | Mục đích |
| --- | --- | --- |
| **Encrypt invocations** | Lần mã hóa dưới một key | Usage bound của thuật toán/mode |
| **Nonce reservations** | Slot/IV đã được cấp cho phép Encrypt | Kiểm soát cấp nonce và hard budget |
| **Successful Encrypt** | Có ciphertext thành công | Theo dõi output, không thay reservation |
| **Failed Encrypt** | Encrypt không có output dùng được | Điều tra; slot đã reserve thường không hoàn lại |
| **Decrypt attempts** | Mọi lần thử giải mã, kể cả tag sai | Abnormal access, forgery/oracle monitoring |
| **Successful Decrypt** | Giải mã và xác thực hợp lệ | Thống kê đọc dữ liệu; không phải Encrypt count |
| **KMS API calls** | GenerateDataKey, Encrypt, Decrypt, ReEncrypt... | Quota, cost, IAM audit; không phải local AES count |
| **Wrap/Unwrap** | KEK được dùng bọc/mở key material | KEK lifecycle và key usage monitoring |
| **Sign** | Private signer tạo chữ ký | Usage/cryptoperiod/abuse, purpose controls |
| **Verify** | Xác minh chữ ký/MAC | Traffic và abuse, không phải private Sign |
| **GenerateMac** | Tạo MAC bằng secret | Message authentication usage |
| **DeriveKey** | Root/IKM tạo subkey theo context | Derived-key population/domain separation |
| **Bytes/blocks** | Tổng lượng dữ liệu dùng một key/mode | Bound theo kích thước ngoài count |
| **Distinct principals/tenants** | Đếm chủ thể/phạm vi sử dụng | Blast radius, least privilege |

**Không cộng tất cả operation rồi so với một giới hạn Encrypt của AES-GCM.** Mỗi primitive có security bounds và ngữ nghĩa khác nhau.

### 2.2. Count không thay quyền truy cập

**Access review** trả lời: ai có thể dùng khóa nào, qua đường quyền nào? **Usage count** trả lời: key đã được dùng bao nhiêu lần và theo ngữ cảnh nào?

Một principal chưa gọi Decrypt nhưng vẫn có quyền thì vẫn cần review. Một principal chỉ Sign một lần trái phép vẫn có thể phát hành artifact giả. Bộ đếm không tự chặn việc **Export raw key**, **CreateGrant/ChangePolicy** hay lấy secret từ heap dump.

### 2.3. Cryptoperiod theo thời gian khác usage limit

Một key có thể:

- Chưa hết một tháng nhưng đã chạm ngân sách Encrypt.
- Đã hết hạn dùng Encrypt dù chỉ được gọi vài lần.
- Retired cho phép toán mới nhưng vẫn cần **Decrypt legacy ciphertext**.
- Bị compromise và phải xử lý ngay dù count mới bằng 1.

Quyết định sử dụng cần xét **time, count/bytes, key state, authorization và security events**, không chỉ tuổi hoặc count.

## 3. Phải đếm theo key material/version, không theo alias

### 3.1. Alias có thể đổi đích

~~~text
billing-active-key -> key-material-v1 (trước rotation)
billing-active-key -> key-material-v2 (sau rotation)
~~~

Hai key versions cần bộ đếm riêng. Nếu gom count theo alias, không thể biết v1 đã dùng bao nhiêu lần, cũng không phát hiện v1 vẫn bị Encrypt sau cutover.

Một key có thể có **KMS resource ID, HSM object handle, alias, replica, imported material ID**. Khi giới hạn phụ thuộc key bytes, **cùng raw key material ở nhiều regions/providers thuộc cùng miền sử dụng mật mã** dù IDs khác nhau.

### 3.2. Những trường hợp dễ sai

| Trường hợp | Sai lầm | Cách kiểm soát |
| --- | --- | --- |
| Alias v1 chuyển sang v2 | Reset/đổi count theo alias | Ghi resolved immutable key version tại operation |
| Cùng AES key import hai vùng | Mỗi vùng có usage/nonce budget riêng | Global material-family registry và nonce ownership |
| DEK cache tại app | KMS không quan sát local Encrypt | Đo ở data plane, tách control plane |
| Disable rồi Enable cùng key | Reset counter về 0 | Counter history gắn vật liệu, không reset |
| Restore VM snapshot cũ | Counter rollback, nonce được dùng lại | Durable allocator/unique nonce namespace |
| Root derive nhiều subkeys | Cộng mỗi data Encrypt vào root count | Root Derive và per-subkey Encrypt riêng |
| KEK wrap nhiều DEKs | Count data Encrypt vào KEK | KEK Wrap/Unwrap khác DEK Encrypt |

Không xuất raw key để hash trực tiếp cho logging. Dùng **trusted inventory, provider references, approved attestation/import evidence và logical material identity**. KCV/fingerprint nếu dùng phải theo profile và đánh giá nguy cơ lộ thông tin; nó không chứng minh entropy hoặc provenance.

## 4. Mục đích kiểm soát: crypto bound, blast radius, audit và operations

Usage count phục vụ ít nhất năm nhóm:

1. **Giới hạn mật mã:** một số thuật toán/mode có giới hạn hoặc mức suy giảm bảo mật theo số bản tin, độ dài, nonce collisions.
2. **Blast radius:** DEK per object khác DEK mã hóa hàng triệu hóa đơn.
3. **Vòng đời:** kích hoạt key mới, retire/rotate, giữ decrypt-only theo retention.
4. **Misuse detection:** Sign/Unwrap/Decrypt đột biến từ workload không phù hợp.
5. **Operations:** KMS/HSM quota, capacity, billing và đánh giá chi phí.

### 4.1. Hard limit, soft alert và rate limit

- **Hard budget:** admission/reservation bắt buộc trước operation, vượt ngưỡng thì fail closed.
- **Soft threshold:** cảnh báo tại các mức như 70%, 85%, 95% để kịp triển khai key mới. Các mức chỉ minh họa vận hành.
- **API rate limit:** giới hạn requests mỗi giây/phút để giảm misuse và bảo vệ hệ thống, **không thay** key lifetime bound.
- **Provider quota/billing:** giới hạn của dịch vụ không mặc nhiên là cryptographic safety bound.

Một key có thể bị throttle vì quota trong khi crypto budget còn nhiều, hoặc cạn crypto budget dù traffic ít.

### 4.2. Đếm sau thao tác không chặn vượt giới hạn

Nếu limit = 1.000 và hai threads cùng đọc count=999, chúng có thể cùng Encrypt trước khi cộng, gây vượt budget. Một timeout sau khi primitive đã chạy nhưng trước ghi counter cũng có thể khiến retry dùng lại nonce.

**Reserve slot atomically trước Encrypt** và coi slot đã được cấp là tiêu thụ ngay cả khi kết quả chưa rõ. Cách này có thể đếm cao hơn completed operations nhưng tránh **tái cấp nonce có khả năng đã dùng**.

## 5. AES-GCM: số lần Encrypt gắn chặt với nonce

AES-GCM là chế độ **authenticated encryption with associated data (AEAD)**:

~~~text
AES key K
+ nonce/IV N
+ AAD A
+ plaintext P
-> ciphertext C + authentication tag T
~~~

Điều kiện nền tảng: **không được tái sử dụng cùng (K, N) cho những phép Encrypt khác nhau**. Lặp nonce dưới cùng key có thể gây hậu quả nghiêm trọng cho confidentiality và integrity.

### 5.1. Random 96-bit nonce

Nếu nonce được sinh **độc lập, phân bố đều 96 bit** cho mỗi Encrypt và xác suất collision còn nhỏ, birthday approximation là:

\[
P(\text{có collision}) \approx \frac{q(q-1)}{2^{97}}
\]

với \(q\) là số phép Encrypt dưới **cùng key material**. Đây chỉ là mô hình collision cho random IV, **không** gồm mọi security bounds theo GCM, độ dài bản tin, tag, IV construction hoặc tiêu chuẩn/provider.

Không tự tuyên bố một ngưỡng như 1 triệu hoặc `2^32` là giới hạn an toàn **chung** cho mọi cấu hình AES-GCM. Policy phải dựa trên mode/profile/IV strategy và các điều kiện áp dụng.

### 5.2. Deterministic IV

Một thiết kế khác có thể cấp **prefix/domain riêng** và counter tăng đơn điệu:

~~~text
Key material V
  -> unique sender/domain prefix under V
  -> durable monotonically increasing counter
  -> IV = prefix || counter
~~~

Muốn đảm bảo uniqueness phải chứng minh:

- Không hai senders nào dùng cùng prefix + counter dưới key V.
- Counter không reset/wrap-around khi restart, backup restore hoặc failover.
- Reservation atomically committed trước khi Encrypt.
- Prefix không được cấp lại khi thay VM, provider, region hoặc import raw key.
- Độ dài layout và usage bounds phù hợp profile.

**AtomicLong trong JVM không giải quyết toàn bộ điều kiện này trong cluster.**

### 5.3. Count và số byte/blocks

Một bản tin 20 byte và một bản tin 1 GB đều có thể là một Encrypt invocation, nhưng lượng blocks/length và giới hạn cơ chế là khác nhau. Nên ghi **message length, total data volume và per-message bounds** trong thiết kế khi thuật toán/profile yêu cầu.

### 5.4. Hai instance, cùng key, cùng IV

~~~text
Cùng AES key K và prefix P:

Pod A: counter=0 -> IV=P||0 -> Encrypt(invoice-A)
Pod B: counter=0 -> IV=P||0 -> Encrypt(invoice-B)

Cặp (K,IV) trùng, dù mỗi pod báo usageCount=1.
~~~

**Cộng dashboard sau sự kiện không ngăn IV reuse.** Cần cơ chế cấp nonce duy nhất toàn miền key material, hoặc DEKs/domain separation hợp lệ.

### 5.5. Decrypt có tiêu thụ Encrypt nonce budget không?

**Không theo nghĩa cấp IV mới.** Decrypt dùng IV đã đi cùng ciphertext. Tuy nhiên vẫn cần đếm **Decrypt attempts, successes, tag failures, IAM denials** để phát hiện dò đoán/oracle/misuse và hỗ trợ đánh giá security profile khi có liên quan.

Không dùng plaintext trước khi GCM tag xác thực, không fallback ECB/CBC hoặc bỏ AAD khi Decrypt bị lỗi.

## 6. Ý nghĩa count thay đổi theo thuật toán và loại khóa

| Key/primitive | Metric chính | Điều không được suy luận |
| --- | --- | --- |
| **AES-GCM DEK** | Encrypt/nonce reservations, bytes, failed Decrypt | KMS Unwrap count không bằng data Encrypt count |
| **AES-KW/KWP KEK** | Wrap/Unwrap, protected DEK population | Không áp nonce assumptions của AES-GCM lên mọi key wrap |
| **AES-GCM wrapping KEK** | Wrap-encrypt/IV reservations, tag failures | Nonce-wrap và nonce-data thuộc các key khác nhau |
| **HMAC key** | GenerateMac/VerifyMac, bytes, caller/purpose | Raw HMAC key của verifier cũng có thể tạo MAC |
| **Ed25519 signing key** | Sign attempts/successes và issuer/purpose | Không áp AES-GCM nonce limit lên Ed25519 |
| **ECDSA signing key** | Sign count, provider nonce health và usage profile | Counter không chứng minh ECDSA nonce an toàn |
| **RSA-PSS key** | Sign invocations và signing context | Không gộp RSA-OAEP usage vào Sign |
| **RSA-OAEP key** | Encrypt/Decrypt hoặc Wrap/Unwrap, errors | OAEP dành cho payload nhỏ/params đúng |
| **HKDF root/IKM** | Derive calls, distinct context/subkeys | Nhiều calls giống nhau có thể ra cùng key |
| **X25519/ECDH static key** | Agreements và session/peer identities | Agreement tự nó không xác thực peer |
| **TLS traffic key** | Protocol records/bytes và key-update events | KMS API count không thay protocol-specific limits |
| **HSM root/recovery** | Admin/derive/import/export/recovery usage | Hiếm dùng không đồng nghĩa không có rủi ro |
| **Public verification key** | Verify traffic, trust registry changes | Verify count không bằng private Sign count |

### 6.1. Chữ ký số

Một private key **Ed25519** hoặc **RSA-PSS** có thể Sign nhiều thông điệp hợp lệ; count có giá trị cho cryptoperiod, anomaly và audit. **Một chữ ký giả duy nhất cũng là sự cố** nếu vượt purpose/approval.

Với **ECDSA**, nonce per-signature rất quan trọng: lỗi hoặc lặp nonce có thể lộ private key. Count Sign không thay provider/implementation nonce correctness; không tự viết ECDSA nonce generator.

**Verify chữ ký số bằng public key** không có nghĩa private key đã được dùng Sign cùng số lần. Theo dõi quyền sửa **JWKS/trust registry** riêng.

### 6.2. HMAC/MAC

Nếu verifier giữ raw HMAC key, nó cũng có thể tính MAC. Provider KMS/HSM có **GenerateMac/VerifyMac APIs tách quyền** có thể giúp giới hạn secret exposure. Count GenerateMac và VerifyMac riêng; theo dõi failed verifications, replay event IDs và key rotation windows.

### 6.3. KDF và key agreement

HKDF cùng IKM/salt/info có thể cho **cùng derived key** khi lặp; vì thế DeriveKey calls không nhất thiết bằng số **subkeys duy nhất**. Ghi domain separation theo purpose/tenant/version. X25519/ECDH cần peer authentication và KDF/key schedule; count handshakes không chứng minh confidentiality.

## 7. KMS/HSM count không bằng count ở ứng dụng

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Java workload
    participant K as KMS/HSM giữ KEK
    participant S as Database
    U->>A: Save invoice
    A->>K: GenerateDataKey / Wrap
    K-->>A: DEK tạm + wrapped DEK
    A->>A: AES-GCM Encrypt under DEK (+1 DEK slot)
    A->>S: Store ciphertext + wrapped DEK
    Note over K: KEK operation / API count theo KMS
    Note over A: Data AES Encrypt count theo local JCA
    U->>A: Read invoice
    A->>S: Load envelope
    A->>K: Unwrap DEK nếu chưa cache
    K-->>A: DEK hoặc operation handle
    A->>A: AES-GCM Decrypt, Verify tag
~~~

Khi ứng dụng cache DEK, **một KMS Unwrap** có thể đi kèm **hàng nghìn local Encrypt operations**. Với envelope encryption:

- **KEK usage**: Wrap/Unwrap hoặc operations KMS theo semantics nhà cung cấp.
- **DEK Encrypt usage**: AES-GCM Encrypt, IV reservations, data volume trong app/provider.
- **DEK Decrypt usage**: Decrypt attempts/successes.
- **Business count**: số hóa đơn/tác vụ, có thể khác vì retries.
- **KMS billable requests**: cost/quota, có thể khác số primitive invocations bên trong.

Một lời gọi API có thể bị từ chối trước crypto, bị retry, thành công nhưng client timeout hoặc gồm nhiều primitive steps. Nếu provider chỉ xuất API counts, ghi rõ **đó là proxy**, không tuyên bố biết chính xác primitive invocations.

### 7.1. Non-exportable KEK vẫn có key-use risk

KMS/HSM giữ KEK non-exportable nhưng principal có quyền **Decrypt/Unwrap** vẫn có thể lấy plaintext DEK theo API và dữ liệu bị ảnh hưởng. Giám sát theo principal, key/version, operation, tenant context và abnormal volume; review cả quyền **CreateGrant/ChangePolicy/AssumeRole** có thể nâng quyền.

KMS encryption context không thay **business authorization principal–tenant–resource** và AAD của data ciphertext.

## 8. Attempts, reservations, successes và failures

~~~mermaid
flowchart TD
    IN["Incoming Encrypt request"] --> AUTH{"Authorized and key active?"}
    AUTH -->|No| DENY["Denied request + audit"]
    AUTH -->|Yes| LIMIT{"Atomic slot reservation within budget?"}
    LIMIT -->|No| STOP["Usage-limit reject + audit"]
    LIMIT -->|Yes| RES["Reserved slot + unique nonce"]
    RES --> ENC["AES-GCM Encrypt"]
    ENC --> OUT{"Cipher succeeds?"}
    OUT -->|Yes| OK["Successful Encrypt +1"]
    OUT -->|No| FAIL["Failed Encrypt +1; slot burned"]
    OK --> AUD["Persist ciphertext + audit"]
    FAIL --> AUD
~~~

### 8.1. Reserve trước Encrypt

Nếu hard limit là 1.000, hai threads cùng thấy count=999 không được cùng Encrypt. **Atomic admission/reservation** cấp tối đa một slot cuối cùng. Count completed chỉ tăng sau phép toán; reserved phải tăng trước khi slot được dùng.

### 8.2. Không hoàn lại slot nếu không chắc thao tác đã xảy ra

Khi timeout sau primitive hoặc trước persist, việc refund slot có thể dẫn đến nonce được cấp lại. **Từ chối tái sử dụng slot đã reserve** là nguyên tắc an toàn, dù counters có thể overestimate successful operations.

### 8.3. Business retries khác crypto invocations

Một request Encrypt có thể hoàn tất nhưng database write fail; retry với **nonce khác** dẫn tới hai crypto Encrypt, dù chỉ một record được lưu. Idempotency key cho HTTP **không phải nonce**. Muốn trả cùng kết quả, có thể lưu/cached **ciphertext hoàn tất** theo request ID nếu được thiết kế, không Encrypt plaintext khác với IV cũ.

## 9. Bộ cấp phát phân tán: nhiều JVM, vùng và bản sao

**AtomicLong chỉ atomic trong một JVM**. Nó không đồng bộ giữa processes, pods, regions, VM snapshots hoặc bản key material được import ở hệ khác.

### 9.1. Các cách thiết kế

- **DEK per-object:** một DEK dùng rất ít operations, dễ giới hạn blast radius và IV usage; tăng số wrapped DEKs/KMS calls.
- **Durable global sequencer:** mọi writers của cùng key material reserve slots/ranges từ hệ thống atomic, bền và chống rollback.
- **Disjoint prefix/domain:** mỗi sender được cấp namespace IV duy nhất dưới key, kết hợp counter monotonic; không cấp lại khi restart/failover.
- **HSM/KMS managed AEAD:** chỉ tin provider đảm bảo IV/usage nếu contract thật sự hỗ trợ, không áp suy luận cho local AES trong JVM.

### 9.2. Block reservation

~~~text
Key material V, hard budget 1,000,000

Worker A reserves [0..999]
Worker B reserves [1000..1999]
Worker C reserves [2000..2999]

A uses 0..501, then crashes.
Remaining [502..999] may be burned; do not return them
to the pool if actual use cannot be proven unambiguously.
~~~

Coordinator phải **commit reservation bền** trước khi trao dải; đảm bảo no duplicate allocations qua failover và không rollback khi restore. Dữ liệu cần gắn immutable key material ID/version, owner/policy, next_counter, max_count và lease/audit references.

### 9.3. Pseudo SQL minh họa

~~~sql
-- Pseudo SQL: atomic durable reservation, engine-specific.
UPDATE key_usage_budget
SET next_counter = next_counter + :block_size
WHERE key_material_version = :version
  AND state = 'ENCRYPT_ALLOWED'
  AND next_counter <= max_counter - :block_size
RETURNING next_counter - :block_size AS first_reserved;
~~~

Nếu không cập nhật dòng nào hoặc transaction commit không chắc chắn, **không dùng range**. Production cần tính đến isolation/linearizability, counter overflow, retries, backup restore, authorization và uniqueness giữa regions.

**Đây không phải một nonce manager production hoàn chỉnh.**

## 10. Usage budget và policy gates

Một policy giả định:

~~~yaml
policyId: billing-data-key-usage-example
keyClass: DEK
algorithmProfile: AES-256-GCM
purpose: invoice-content-encryption
counterIdentity: immutable-key-material-version
countedOperation: ENCRYPT_NONCE_RESERVATION
scope: all-writers-sharing-this-key-material
nonceConstruction: approved-unique-IV-design
maxReservationsPerMaterial: 1000000 # Ví dụ nội bộ; KHÔNG phải ngưỡng GCM chung
softAlertsAtPercent: [70, 85, 95]
hardStop: true
nearLimitAction: prepare-new-DEK-and-switch-new-writes
atLimitAction: deny-new-encrypt-allow-approved-legacy-decrypt
evidence:
  - key-version-registry
  - reservation-ledger
  - effective-writer-inventory
  - nonce-allocation-design
~~~

**1.000.000 ở đây chỉ là ví dụ chính sách**, không phải giới hạn an toàn phổ quát của AES-GCM. Mức thật phải dựa trên algorithm/mode, IV method, message bounds, security requirements và tài liệu provider/profile.

### 10.1. Predicate cho new Encrypt

~~~text
Allow a new Encrypt only when:
  principal/key/tenant/purpose authorized
  AND key state == ACTIVE_FOR_ENCRYPT
  AND now < approved cryptoperiod end
  AND reserved slots < approved budget
  AND message length/aggregate bytes inside bounds
  AND unique-IV allocation remains sound
  AND key not revoked/compromised
~~~

Nếu không đủ điều kiện: fail closed, **không dùng hard-coded fallback key**. Key cũ có thể vẫn cần Decrypt các bản mã lịch sử theo đúng retention.

### 10.2. Soft warnings và time-to-exhaustion

Cảnh báo ở 70% hoặc 95% chỉ hữu ích nếu đủ thời gian để tạo/kiểm tra key mới, cập nhật KMS policies, chuyển writers, bảo đảm old ciphertext đọc được và thử restore. Nên theo dõi **usage velocity, remaining slots, estimated time to limit** và workload traffic bursts.

### 10.3. Ba nhóm trigger độc lập

1. **Time-based:** hết cryptoperiod cho new Encrypt/Sign.
2. **Count/volume-based:** gần/hết usage bound.
3. **Event-based:** nonce collision, raw key compromise, IAM abuse, RNG failure hoặc provider incident.

Khi có compromise, xử lý ngay dù usage count rất thấp.
## 11. Thiết kế measurement: nguồn sự thật và độ tin cậy của counter

Một hệ thống có thể có nhiều chỉ số khác nhau, nhưng phải xác định **bộ đếm nào được quyền quyết định admission**.

| Nguồn | Có thể cung cấp | Giới hạn |
| --- | --- | --- |
| **Crypto library wrapper** | Local Encrypt/Decrypt attempts, bytes, key version | Có thể bị bypass bởi code path khác, local-only |
| **Durable reservation ledger** | Dải nonce slots đã cấp, high-watermark | Không tự chứng minh application thực sự sử dụng IV chính xác |
| **KMS/HSM audit log** | API calls, principal, key usage, state, errors | Không thấy những Encrypt local sau Unwrap DEK |
| **Application business event** | Số invoices/files tạo thành công | Không đếm được internal retries hoặc extra crypto invocations |
| **IAM/key policy snapshot** | Ai được phép dùng key | Không chứng minh ai đã thực hiện bao nhiêu |
| **Key inventory** | Owner, material version, purpose, cryptoperiod | Không tự là transactional counter |
| **Observability platform** | Trends, alerts, anomaly investigation | Metrics có thể mất, duplicate, bị delay |
| **HSM module enforcement** | Operations bị từ chối/cho phép theo provider | Có thể không hỗ trợ đúng per-key limit mong muốn |

### 11.1. Admission source of truth

Với hard Encrypt budget, **prometheus metric hoặc tập log bất đồng bộ không đủ làm nguồn quyết định**. Nó có thể:

- Được cập nhật sau Encrypt và đến chậm.
- Mất events khi collector restart.
- Đếm lặp do retry event delivery.
- Trộn key aliases hoặc dimensions.
- Bị reset khi process/pod khởi động lại.

Chọn **atomic per-material reservation state** hoặc một cryptographic provider có guarantee tương đương làm nguồn admission; metrics/audit là hệ bổ trợ để giám sát và đối soát.

### 11.2. Exactly once thường là mục tiêu sai

Trong hệ phân tán, một request có thể hoàn thành nhưng phản hồi bị mất. Tính đúng của crypto budget thường cần **at-most-once allocation của từng nonce/slot**, không nhất thiết có **exactly-once business event**.

Một reservation bị “bỏ phí” được xem là tiêu hao ngân sách, dù ciphertext chưa được lưu. Với thuật toán nhạy nonce, **chấp nhận overcount để tránh undercount** khi kết quả không chắc chắn là lựa chọn bảo thủ.

### 11.3. Bất biến cần ghi thành test

1. Mỗi **(key material version, nonce)** chỉ được cấp để Encrypt tối đa một lần.
2. Không được tăng counter vượt hard budget.
3. Không phát slot nếu key retired/disabled/revoked cho new Encrypt.
4. Reservation không được rollback khi process/DB snapshot cũ trở lại.
5. Không có Encrypt ngoài đường wrapper/allocator được kiểm soát.
6. Active key version được resolve từ trusted policy, không từ user-provided alias.
7. Không xuất secret vào metrics/evidence.
8. Audit records có provenance và trace/correlation ID.
9. Nếu state không chắc chắn, **fail closed**; không suy đoán next nonce.

## 12. Schema metadata và audit: không chỉ một số nguyên

Một snapshot counter mẫu:

~~~yaml
keyMaterialVersionId: aes-dek-billing-v7
keyClass: DEK
keyAlgorithmProfile: AES-256-GCM
purpose: invoice-content-encryption
environment: production
tenantScope: tenant-A
ownerRole: billing-platform
keyState: ACTIVE_FOR_ENCRYPT
counterScope: all-authorized-encrypters-using-this-material
counterType: ENCRYPT_NONCE_RESERVATION
allocatorRef: "nonce-allocator://billing-v7"
reservedSlots: 740000
successfulEncryptsObserved: 739410
failedEncryptsObserved: 120
unreconciledSlots: 470
approvedMaxReservations: 1000000
bytesEncryptedObserved: 2147483648
snapshotTime: "2026-11-28T03:00:00Z"
policyVersion: "billing-key-usage-policy-v2"
evidenceSourceRef: "evidence://allocator-snapshot"
counterHealth: COMPLETE_FOR_DEFINED_SCOPE
~~~

Số liệu **giả định để học**, không phải policy khuyến nghị hay tình hình thực tế. Phân biệt reserved (nguồn admission) với successful Encrypt observed (telemetry có thể thiếu): `unreconciledSlots` là signal để kiểm tra, **không được tự trừ khỏi reserved**.

### 12.1. Audit event cho một operation

~~~json
{
  "eventType": "CRYPTO_USAGE_RESERVED",
  "eventId": "event-example-93821",
  "keyMaterialVersion": "aes-dek-billing-v7",
  "operation": "ENCRYPT",
  "reservationRef": "allocation/billing-v7/segment-9",
  "scope": {"service": "billing", "environment": "production"},
  "principalRef": "workload/billing-writer",
  "policyVersion": "billing-key-usage-policy-v2",
  "decision": "ALLOW",
  "observedAt": "2026-11-28T03:00:00Z",
  "containsRawKeyMaterial": false
}
~~~

Không log **raw DEK/KEK, HMAC secret, private key, nonce seed/hidden secret, plaintext production hoặc token**. IV của AES-GCM thường không bí mật, nhưng logs chứa IV và tenant/object metadata vẫn cần quyền/retention phù hợp. Không ghi dữ liệu nhạy cảm vào AAD hoặc KMS encryption context rồi giả định chúng đã được mã hóa.

### 12.2. Cardinality và privacy

Không gắn hàng triệu object IDs vào nhãn metrics kiểu `key_usage{objectId=...}`; hệ thống observability sẽ chịu **cardinality explosion** và lộ metadata. Chọn labels có cardinality kiểm soát được (service, key class, key version, operation, environment, outcome). Đưa correlation IDs chi tiết vào **audit logs có hạn chế quyền**.

### 12.3. Đối soát nhiều nguồn

Có thể kiểm tra:

~~~text
Durable reserved slots >= observed successful Encrypts
Observed KMS Unwrap operations != local DEK Encrypt operations
Latest key inventory version == version attached to counters
Decommissioned workload should not generate new key usage
Denied Encrypts after limit should increase alarm, not key consumption
~~~

Tuy nhiên không có đẳng thức exact tuyệt đối nếu telemetry bị mất, counters khác scope, provider có internal retries hoặc dữ liệu đến chậm. Ghi **mức bao phủ và độ tin cậy của evidence**; không tự báo PASS khi thiếu một region.

## 13. Kiểm soát quyền xem, ghi và reset counter

Bộ đếm có giá trị bảo mật phải được bảo vệ tương tự một **control-plane primitive**.

### 13.1. Các quyền tối thiểu

- **Encryption service**: có thể yêu cầu reserve nonce trong key scope được phép; không được sửa budget hoặc reset counter.
- **Key owner**: phê duyệt purpose, usage budget và key rotation policy; không cần raw DEK.
- **KMS/HSM custodian**: quản lý key lifecycle và availability theo change approval; không mặc nhiên Decrypt data.
- **Security engineer**: review ngưỡng, drift và incidents, không tự cấp quota vô hạn.
- **Auditor**: read-only usage evidence và policy history.
- **Administrator**: thay policy/allocator theo SoD, approval và audit; không được tự chỉnh logs rồi tự xác nhận.

Một role có thể **UpdateUsageLimit, CreateGrant, ChangeKeyPolicy hoặc sửa allocator state** có thể dẫn đến vượt bound dù không trực tiếp gọi Encrypt; access review cần xét đường nâng quyền gián tiếp.

### 13.2. Counter reset không làm vật liệu khóa mới

Nếu count đã gần limit, **không sửa counter về 0** rồi tiếp tục dùng cùng raw key. Đổi tên alias, import key sang region mới, xóa row trong database hoặc restart JVM đều **không reset lịch sử cryptographic use**.

Cách chính xác nếu cần ngân sách mới: **sinh vật liệu khóa mới/derived key mới với domain separation phù hợp và được phê duyệt**, chuyển writers, giữ old key cho operations lịch sử theo policy.

### 13.3. Tenant isolation

Một key có thể phục vụ nhiều tenants. Count nên gắn per-tenant để giám sát abuse nhưng **hard cryptographic budget phải bao phủ tổng thể mọi dùng chung material**. Nếu mỗi tenant có counter 100.000 nhưng tất cả dùng chung một AES key, không thể coi mỗi tenant được ngân sách mật mã hoàn toàn độc lập.

Đồng thời business authorization principal→tenant→resource vẫn bắt buộc trước khi Encryption/Decryption; AAD hoặc KMS encryption context giúp ràng buộc metadata, không thay IAM và business policy.

## 14. Java 17: usage counter AES-GCM với atomic reservation trong một JVM

Ví dụ sau dùng **JCA/JCE chuẩn**, chạy trên JDK 17 với provider hỗ trợ AES-256-GCM. Nó tạo một DEK local, đặt hard budget **3 lần Encrypt**, dùng `AtomicLong` để reserve một slot trước Encrypt, dựng IV 96 bit từ **prefix 4 byte + counter 8 byte** và thử tác vụ sau khi budget hết.

**Phạm vi chỉ là một JVM và một DEK mới sinh ở lần chạy này.** Prefix tạo bằng SecureRandom và state volatile **không tạo thành phương án nonce production trên các processes dùng chung material**. Nếu key được persist/import/replicate, cần durable global allocator hoặc cấu trúc nonce có bằng chứng không trùng toàn miền.

### 14.1. Mã Java độc lập

Lưu nội dung vào `KeyUsageCountDemo.java` để biên dịch bằng JDK 17 khi thực hành.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class KeyUsageCountDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    record CipherPacket(
        String keyVersion,
        byte[] nonce,
        byte[] ciphertextAndTag
    ) {}

    static final class ManagedDek {
        private final String immutableVersion;
        private final SecretKey key;
        private final byte[] prefix = new byte[4];
        private final long maxReservations;

        // Chỉ atomic trong cùng JVM. Không bền sau restart.
        private final AtomicLong nextSlot = new AtomicLong();
        private final LongAdder encryptAttempts = new LongAdder();
        private final LongAdder encryptCompleted = new LongAdder();
        private final LongAdder encryptDenied = new LongAdder();
        private final LongAdder decryptAttempts = new LongAdder();
        private final LongAdder decryptCompleted = new LongAdder();

        ManagedDek(
            String immutableVersion,
            SecretKey key,
            long maxReservations
        ) {
            if (immutableVersion == null
                    || immutableVersion.isBlank()
                    || key == null
                    || maxReservations <= 0) {
                throw new IllegalArgumentException(
                    "Invalid key usage policy");
            }
            this.immutableVersion = immutableVersion;
            this.key = key;
            this.maxReservations = maxReservations;

            // Demo: một instance duy nhất sở hữu DEK mới.
            // Production: prefix phải được cấp duy nhất dưới
            // cùng key material trên tất cả writers/restarts.
            RNG.nextBytes(prefix);
        }

        private long reserveSlot() {
            for (;;) {
                long current = nextSlot.get();
                if (current >= maxReservations) {
                    encryptDenied.increment();
                    throw new IllegalStateException(
                        "Encryption usage limit reached");
                }
                // CAS ngăn hai threads giữ cùng slot trong JVM.
                if (nextSlot.compareAndSet(current, current + 1)) {
                    return current;
                }
            }
        }

        private byte[] nonceFor(long slot) {
            byte[] iv = new byte[NONCE_BYTES];
            ByteBuffer.wrap(iv)
                .put(prefix)
                .putLong(slot);
            return iv;
        }

        CipherPacket encrypt(
            byte[] plaintext,
            byte[] aad
        ) throws GeneralSecurityException {
            if (plaintext == null || aad == null) {
                throw new IllegalArgumentException(
                    "Inputs are required");
            }

            encryptAttempts.increment();
            long slot = reserveSlot(); // Burn slot on later failure.
            byte[] iv = nonceFor(slot);

            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, iv));
            cipher.updateAAD(aad);
            byte[] output = cipher.doFinal(plaintext);
            encryptCompleted.increment();

            return new CipherPacket(immutableVersion, iv, output);
        }

        byte[] decrypt(
            CipherPacket packet,
            byte[] expectedAad
        ) throws GeneralSecurityException {
            decryptAttempts.increment();
            if (packet == null || expectedAad == null
                    || !immutableVersion.equals(packet.keyVersion())
                    || packet.nonce() == null
                    || packet.nonce().length != NONCE_BYTES) {
                throw new SecurityException(
                    "Untrusted envelope/key version");
            }

            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, packet.nonce()));
            cipher.updateAAD(expectedAad);
            byte[] plaintext = cipher.doFinal(
                packet.ciphertextAndTag());

            decryptCompleted.increment();
            return plaintext;
        }

        void showSafeMetrics() {
            System.out.println(
                "Encrypt reserved: " + nextSlot.get());
            System.out.println(
                "Encrypt attempted: " + encryptAttempts.sum());
            System.out.println(
                "Encrypt completed: " + encryptCompleted.sum());
            System.out.println(
                "Encrypt denied: " + encryptDenied.sum());
            System.out.println(
                "Decrypt attempted: " + decryptAttempts.sum());
            System.out.println(
                "Decrypt completed: " + decryptCompleted.sum());
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator =
            KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        SecretKey dek = generator.generateKey();

        // Demo policy: at most 3 new AES-GCM encryptions.
        ManagedDek managed =
            new ManagedDek("billing-dek-version-1", dek, 3);

        byte[] aad = "tenant-A|invoice-154|schema-v1"
            .getBytes(StandardCharsets.UTF_8);
        byte[] message = "non-sensitive-demo-payload"
            .getBytes(StandardCharsets.UTF_8);

        CipherPacket a = managed.encrypt(message, aad);
        managed.encrypt(message, aad);
        managed.encrypt(message, aad);

        // AES Encrypt #4 bị từ chối trước khi tạo IV/output.
        try {
            managed.encrypt(message, aad);
            throw new AssertionError("Limit was not enforced");
        } catch (IllegalStateException expected) {
            System.out.println(
                "Fourth Encrypt: REJECTED_BY_USAGE_LIMIT");
        }

        // Old ciphertext vẫn có thể Decrypt sau hard stop
        // nếu policy cho phép legacy Decrypt.
        byte[] recovered = managed.decrypt(a, aad);
        if (!MessageDigest.isEqual(message, recovered)) {
            throw new AssertionError("Decryption mismatch");
        }
        System.out.println("Legacy Decrypt: PASS");

        // Sai AAD phải bị AEAD reject; không trả plaintext.
        byte[] wrongAad = "tenant-B|invoice-154|schema-v1"
            .getBytes(StandardCharsets.UTF_8);
        try {
            managed.decrypt(a, wrongAad);
            throw new AssertionError("Wrong AAD was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD: REJECTED");
        }

        managed.showSafeMetrics();
        // Không in raw AES key hoặc customer plaintext.
    }
}
~~~

Kết quả dự kiến:

~~~text
Fourth Encrypt: REJECTED_BY_USAGE_LIMIT
Legacy Decrypt: PASS
Wrong AAD: REJECTED
Encrypt reserved: 3
Encrypt attempted: 4
Encrypt completed: 3
Encrypt denied: 1
Decrypt attempted: 2
Decrypt completed: 1
~~~

### 14.2. Những nguyên tắc được minh họa

1. **Key version** gắn với DEK, không dựa riêng trên alias có thể đổi.
2. **Encrypt slot được reserve trước khi chạy AES-GCM**, qua CAS trong JVM.
3. **Hard limit** chỉ cho phép ba slots, thao tác thứ tư thất bại.
4. **Nonce khác nhau cho mỗi slot:** 4 byte prefix và 8 byte counter.
5. **Không recycle slot** khi xảy ra lỗi sau reservation.
6. **Encrypt/Decrypt counts riêng biệt:** hard limit cho new Encrypt không tự cấm đọc dữ liệu cũ.
7. **Attempted/completed/denied counts khác nhau:** rejected operation không làm tăng completed.
8. **AAD-data** được kiểm tra khi Decrypt; sai tenant context dẫn đến tag failure.
9. **Đầu ra chỉ là metrics**, không in raw DEK/nonce prefix secret, private key hoặc production data.
10. **Crypto operation không phụ thuộc dashboard**: admission nằm trên đường Encrypt.

### 14.3. Những điều ví dụ KHÔNG chứng minh

- **Không có distributed/global nonce manager:** prefix random 4 byte không bảo đảm tuyệt đối uniqueness giữa nhiều JVM dùng cùng raw key.
- **Không bền qua restart/restore:** AtomicLong và prefix mất trạng thái. Vì demo tạo DEK mới mỗi lần chạy, nó không nhằm phục hồi old key. Production **không được restart rồi dùng lại old DEK với counter=0**.
- **Không có KMS/HSM thật:** local AES SecretKey có thể nằm trong JVM, không có KEK/DEK wrapping, IAM, grants hoặc attestation.
- **Không có cryptographic proof về RNG entropy**, không chứng minh nonce construction đủ cho mọi traffic profile.
- **Không giới hạn per-message size/bytes** ngoài số Encrypt; GCM cần thêm bounds phù hợp.
- **Không kiểm tra concurrency bằng test suite**; CAS có ngữ nghĩa đúng trong JVM nhưng không bảo vệ các code paths khác dùng raw key.
- **Không có tenant authorization**: trusted AAD trong ví dụ phải được dựng từ resource identity đã xác thực ngoài thực tế.
- **Không bảo vệ array mutability:** record chứa byte[], cần defensive copy/serialization validation trong production.
- **Không quản lý DEK cache, heap dumps, log leakage hoặc secure deletion**.
- **Không có audit store bất biến hoặc independent readback**; LongAdder metrics là số liệu process-local.
- **Không thực hiện rotation/rewrap/re-encrypt/backup** và không xử lý key compromise.
- **Không đảm bảo GCM usage limit theo bất kỳ chuẩn cụ thể nào**: budget=3 chỉ để quan sát hard-stop logic.

**Đừng chuyển nguyên mẫu Java này thành crypto service production**. Điểm cốt lõi là **reservation trước operation, không cấp trùng IV và phân biệt metrics**, rồi thực hiện các bảo đảm phân tán/lifecycle ở kiến trúc thật.

## 15. Rotation khi đạt usage budget

~~~mermaid
flowchart LR
    A["Key v1 ACTIVE_FOR_ENCRYPT"] --> T{"Time/count/incident trigger?"}
    T -->|Near soft limit| PRE["Preprovision & validate v2"]
    PRE --> IAM["IAM + key registry + owner approval"]
    IAM --> SWITCH["Switch new writes to v2"]
    SWITCH --> RET["v1 legacy Decrypt/Unwrap only"]
    RET --> DEP["Dependency inventory + backup/restore"]
    DEP --> END["Retire/destroy v1 when safe"]
    T -->|Hard limit or compromise| STOP["Fail closed new v1 Encrypt"]
    STOP --> PRE
~~~

### 15.1. Không reset counter khi rotate alias

Khi active alias đổi v1→v2, **counter v1 giữ nguyên**; v2 có material mới và budget mới theo policy. Các writers phải resolve version đúng; nếu một pod vẫn encrypt với v1 sau cutover, hệ thống cần phát hiện và từ chối khi v1 không còn trạng thái cho phép.

### 15.2. KEK rewrap khác DEK re-encrypt

- **Rotate KEK / rewrap:** Wrap lại **cùng DEK** dưới KEK mới; data ciphertext có thể không đổi. **DEK usage count không reset** vì material DEK vẫn cũ.
- **Rotate DEK / re-encrypt:** Tạo DEK mới và Encrypt lại dữ liệu với nonce/tag mới; đây mới là material mới cho data-encryption usage budget.
- **Rotate signing key:** Private signer version mới; trust distribution và Verify historical artifacts cần quản lý riêng.
- **KDF root rotation:** Có thể ảnh hưởng nhiều derived keys và data; cần dependency graph.

**Không coi rewrap KEK là giải pháp cho DEK vượt giới hạn Encrypt hoặc nonce collision.**

### 15.3. Giữ decrypt-only sau khi ngừng Encrypt

Key v1 đã hết usage budget **đối với new Encrypt** vẫn có thể cần Decrypt các ciphertext cũ, theo policy. Ngừng Encrypt không mặc định đồng nghĩa **DestroyKey ngay**. Trước destruction cần kiểm kê wrapped DEKs, backups, data retention, signatures/trust và restore tests.

### 15.4. Khi nghi compromise

Nếu raw DEK đã lộ hoặc đã xảy ra nonce reuse, chỉ chuyển alias sang key mới **không sửa những bản ciphertext cũ đã lộ**. Có thể cần **re-encrypt dưới DEK mới** và điều tra data exposure. Nếu KEK bị lộ, rewrap DEK hiện tại không xóa các **old wrapped DEKs** attacker đã sao chép.

Khi IAM/credential bị compromise nhưng raw key chưa chứng minh lộ, đánh giá **KMS operations, plaintext DEKs đã unwrap, data impact và grants** trước khi chọn xử lý. Không chỉ “tăng usage limit” để vượt qua cảnh báo.

## 16. Điều tra count bất thường bằng audit

### 16.1. Những dấu hiệu nên cảnh báo

- Encrypt slots tăng nhanh hơn dự kiến hoặc không tương xứng business activity.
- Sign/GenerateMac tăng đột biến từ workload chưa được phê duyệt.
- Decrypt/Unwrap nhiều tenant từ một principal bất thường.
- VerifyMac failures hoặc GCM tag failures tăng.
- Key v1 còn được dùng Encrypt sau rotation/cutover.
- Usage xuất hiện trên key **DISABLED/REVOKED** trong local cache hoặc key copy ngoài provider.
- Counter rollback sau restore hoặc timestamp out-of-order.
- Nhiều regions dùng cùng raw key nhưng mỗi nơi chỉ xuất local counts.
- KMS grant tăng rộng và usage từ principals mới.
- Số “successful Encrypt” vượt “reserved slots” trong cùng scope — có thể có bypass hoặc measurement mismatch.
- Tần suất nonce reservations vượt budget trước khi monitoring báo động.
- Dịch vụ đã decommission nhưng DEK usage vẫn xuất hiện.
- Recovery/break-glass key được dùng ngoài approved window.

### 16.2. Không phán đoán từ một spike

Ví dụ một job re-encrypt hợp lệ có thể tạo nhiều Encrypt operations trong thời gian ngắn. Cần xem:

- Ticket/approval và workstream.
- Principal, environment, tenant, key ID/version.
- Operation type, attempted/successful counts và data volume.
- Audit KMS/HSM và application request IDs.
- Các thay đổi policy/alias/grants gần thời điểm spike.
- Key inventory/counter scope và consistency của evidence.

Nếu có dấu hiệu lạm dụng, chuyển **incident response** trước khi điều tra xong toàn bộ business reason.

### 16.3. Không dùng một dashboard thiếu scope để tuyên bố tuân thủ

Ví dụ chỉ đo KMS production account nhưng DEK cũng được export trong batch worker offline. Khi ấy conclusion đúng là **INSUFFICIENT_EVIDENCE** cho global material usage, không phải “dưới ngưỡng”.

Để hard bound đáng tin, phải có **đường không thể bypass, global reservation invariant và bằng chứng bao phủ mọi nơi cùng material được dùng**.
## 17. Tình huống A: hai pods dùng cùng AES key, counter trùng sau restart

### 17.1. Bối cảnh

Một đội triển khai BillingService với hai pods A và B. Cả hai có cùng DEK-v4 từ KMS; mỗi pod tạo AES-GCM nonce theo công thức:

~~~text
IV = fixed-prefix || local-counter
local-counter starts at 0 on process start
~~~

Trong lúc triển khai, pod A và B cùng bắt đầu counter=0. Vì prefix giống nhau, cả hai có thể Encrypt các plaintext khác nhau dưới **cùng (DEK-v4, IV)**.

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant K as Shared AES-GCM DEK-v4
    participant S as Storage / Metrics
    A->>K: Encrypt(invoice-1), nonce=P||0
    B->>K: Encrypt(invoice-2), nonce=P||0
    K-->>A: ciphertext-A, tag-A
    K-->>B: ciphertext-B, tag-B
    A->>S: usage_A=1
    B->>S: usage_B=1
    Note over S: Tổng usage=2 nhưng đã có nonce reuse
~~~

### 17.2. Vì sao count không phát hiện kịp?

Dashboard có thể tính đúng **2 lần Encrypt** nhưng không biết cả hai đã sử dụng **cùng nonce**. Việc cộng hai bộ đếm độc lập chỉ mang tính **phát hiện sau sự kiện**, không bảo vệ tính duy nhất của IV.

Nếu mỗi pod tự giữ một counter, ứng dụng không có bảo đảm toàn cluster. Đặc biệt sau crash/rollback, một pod có thể **lặp lại dải slot** đã cấp trước đó.

### 17.3. Cách xử lý

1. Chặn new Encrypt dưới DEK-v4 và cô lập nguyên nhân cấp IV.
2. Thu thập evidence về key version, nonce allocation paths và ciphertext/objects đã được tạo.
3. Phân tích liệu đã xảy ra nonce collision dưới cùng key; nếu có, kích hoạt security incident assessment.
4. Tạo **DEK-v5** theo policy mới, chuyển new writes sang vật liệu mới.
5. Đánh giá dữ liệu bị ảnh hưởng; cân nhắc re-encrypt dữ liệu với DEK mới và lưu audit.
6. Triển khai durable global allocator hoặc DEK-per-object (hoặc verified disjoint prefix domains).
7. Kiểm tra concurrency, rolling restart, crash, retry, multi-region và backup restore.
8. Chỉ resume khi có bằng chứng nonce uniqueness trên toàn miền key material.

**Không sửa bằng cách chỉ reset counter hoặc thay KEK bọc DEK-v4.** Raw DEK-v4 vẫn là key đã bị sử dụng với IV trùng.

## 18. Tình huống B: dashboard KMS cho thấy ít lượt, data plane dùng hàng triệu lần

### 18.1. Bối cảnh

PaymentService gọi KMS `GenerateDataKey` để lấy DEK và wrapped DEK. Sau đó dùng DEK để Encrypt một batch lớn, có cơ chế cache trong JVM.

Trong một ngày:

~~~text
KMS GenerateDataKey/Unwrap calls = 800
Application AES-GCM Encrypt = 2,400,000
Business payment objects created = 2,350,000
Some Encrypts were retries or temporary outputs
~~~

**800 không phải số lần AES-GCM data Encrypt**. 2,35 triệu business objects cũng không bằng 2,4 triệu crypto operations.

### 18.2. Sai lầm dễ mắc

Đội security lấy KMS metrics làm chỉ số cryptographic usage rồi cho rằng mọi DEKs đều an toàn. Nhưng có thể:

- Một DEK được tái dùng cho nhiều batches lớn.
- Local AES Encrypt chạy trên hàng chục pods và không chia sẻ nonce allocator.
- KMS logs chỉ ghi lần bảo vệ/unwrap key material.
- Cache làm giảm Unwrap nhưng kéo dài thời gian plaintext DEK tồn tại trong RAM.
- KMS key bị disabled nhưng cached DEK vẫn dùng tạo ciphertext mới ngoài luồng KMS.

### 18.3. Thiết kế đo đúng

- Counter **KMS KEK operations** theo key ID và principal.
- Counter **DEK Encrypt invocations/nonce reservations** ở đúng data plane.
- Gắn mỗi DEK với immutable version và scope, không chỉ KMS alias.
- Theo dõi processed bytes, failed/denied operations và cache lifetime.
- Định nghĩa **key-usage policy** theo DEK granularity/nonce profile.
- Đối soát business objects để phát hiện bất thường, không dùng chúng thay Crypto count.
- Khi key compromised, đánh giá cả **KMS calls và plaintext DEKs đã cache**.

## 19. Tình huống C: signing key bất ngờ tăng từ 50 lên 50.000 lần Sign

### 19.1. Bối cảnh

Một HSM giữ private signing key của release pipeline. Bình thường service chỉ Sign vài chục manifests mỗi ngày. Sau một sự cố cấp quyền, role của hệ thống debug có thể gọi `Sign` mà không cần release approval.

Monitoring ghi nhận:

~~~text
key = release-signing-v3
operation = SIGN
baseline = ~50/day
observed = ~50,000/day
caller = unexpected-debug-role
~~~

### 19.2. Ý nghĩa count

Số Sign tăng mạnh là **indicator of compromise hoặc misuse**, nhưng tự nó không chứng minh message nào là giả. Trong nhiều giao thức, chữ ký Ed25519 được tạo hợp lệ cho mỗi message dù attacker không được business approval.

Điều cần kiểm tra:

- Payload/purpose/issuer của các ký số bất thường.
- Principal/role assumption và đường quyền Sign.
- Audit HSM Sign events và approved release tickets.
- Chữ ký đã được công bố/phát hành ra bên ngoài chưa?
- Trust registry/certificates/public keys có bị thay đổi không?
- Key có bị dùng sau khi **retired hoặc revoked** không?

### 19.3. Phản ứng

Khi có dấu hiệu misuse, **không chờ đủ usage threshold**; kích hoạt incident response, khóa quyền Sign trái phép, bảo vệ evidence và đánh giá signed artifacts. Nếu cần, tạo signer version mới và thực hiện **trust rollover/revocation**. Không coi “Sign count chưa đạt giới hạn AES-GCM” là lý do an toàn: các giới hạn này không liên quan.

## 20. Tình huống D: khôi phục database làm counter rollback

### 20.1. Bối cảnh

Một service dùng một shared AES-GCM DEK và lưu `nextCounter` trong database. Lúc 10:00, counter đã là 100.000; đến 10:05 DB gặp sự cố và được restore snapshot lúc 09:00, khi counter mới 90.000.

Các ciphertext tạo trong khoảng 09:00–10:00 vẫn có bản sao ở nơi khác. Nếu service tiếp tục từ 90.000, nó có thể **cấp lại IV đã dùng**.

### 20.2. Vì sao đây là sự cố mật mã?

Usage ledger rollback có thể nguy hiểm **ngay cả khi ciphertext database chính đã bị rollback cùng lúc**: attacker, replica, backup hoặc downstream system có thể còn giữ ciphertext cũ. Key/IV reuse không được hợp thức hóa bằng cách “bản cũ không còn trong database chính”.

### 20.3. Thiết kế phòng ngừa

- Bộ cấp nonce có **durable monotonic state chống rollback**, tách khỏi snapshot dễ lùi.
- Khi cần phục hồi, bảo đảm high-watermark **không nhỏ hơn mọi slot đã từng cấp**.
- Nếu không xác định được high-watermark, fail closed và **chuyển sang vật liệu khóa mới**.
- Không tự giảm counter theo số object còn tồn tại.
- Đánh giá preallocated ranges của những workers trước sự cố.
- Kiểm tra region failover, DR restore và data consistency trong test định kỳ.

**Usage count là trạng thái bảo mật, không chỉ là một hàng dữ liệu có thể được rollback như cache.**

## 21. Tình huống E: rotate KEK rồi nhầm rằng DEK có lại nguyên ngân sách

### 21.1. Bối cảnh

Một hệ thống envelope encryption có:

~~~text
DEK-7 encrypts 600,000 records
KEK-v1 wraps DEK-7

Rotation:
KEK-v2 replaces KEK-v1
DEK-7 is rewrapped, raw DEK bytes do not change
~~~

Một đội phát triển đặt lại `encryptCount(DEK-7)=0` vì bản wrapped DEK bây giờ mang KEK version mới.

### 21.2. Sai ở đâu?

**Rewrap thay lớp bảo vệ DEK, không thay key material DEK**. Mọi lịch sử AES-GCM Encrypt dưới DEK-7 vẫn tồn tại. Nếu reset count/nonce sequence, nguy cơ cấp IV lặp và vượt usage bound là nghiêm trọng.

### 21.3. Quy tắc đúng

- Counter Encrypt gắn với **DEK material version**, không gắn KEK hiện tại.
- Counter Wrap/Unwrap gắn với **KEK material/version**.
- Rewrap thay wrapped blob/KEK reference, **không thay data ciphertext** và không reset DEK count.
- Nếu muốn DEK mới, phải **generate DEK mới** và mã hóa lại dữ liệu tương ứng theo policy.
- Old KEK có thể vẫn cần Unwrap backup cũ; không destroy trước dependency/restore checks.

### 21.4. Kết nối với recovery

Khi một DEK/KEK đạt cryptoperiod hoặc usage budget, không được tự xóa keys chỉ để dashboard “xanh”. Phải xét wrapped DEKs, data ciphertext, nonce/tag/AAD, key versions, backups, retention và quyền restore.

## 22. Quy trình vận hành khi count gần ngưỡng hoặc có bất thường

~~~mermaid
flowchart TD
    OBS["Usage telemetry / reservation budget"] --> G{"Loại trigger?"}
    G -->|"Soft threshold"| PRE["Plan new key + notify owner"]
    G -->|"Hard limit"| STOP["Reject new operations on old key"]
    G -->|"Nonce reuse / compromise"| INC["Incident response + containment"]
    PRE --> TEST["Create/validate new key in KMS/HSM"]
    TEST --> IAM["Approve IAM + update key registry"]
    IAM --> SWITCH["Switch new Encrypt/Sign to new material"]
    STOP --> SWITCH
    SWITCH --> HIST["Keep controlled legacy Decrypt/Verify"]
    HIST --> REST["Dependency inventory + backup restore"]
    REST --> CLOSE["Retirement only after approval"]
    INC --> ASSESS["Assess exposed DEKs/data/signatures"]
    ASSESS --> REM["Rekey / re-encrypt / trust rotation as needed"]
    REM --> TEST
~~~

### 22.1. Trước khi hết ngân sách

1. Kiểm tra count scope/identity/algorithm có chính xác không.
2. Đối soát logs với reservations và mọi writers/regions.
3. Ước lượng tốc độ tiêu thụ và thời gian còn lại.
4. Tạo và validate key version mới, kiểm tra owner/custodian.
5. Cấp IAM operations theo least privilege, chuẩn bị cutover.
6. Giảm traffic/khối lượng nếu chính sách cho phép mà không bỏ bảo mật.
7. Định nghĩa key old **decrypt-only** và thử với ciphertext thực theo phạm vi được duyệt.
8. Ghi audit, changes, approvals và rollback plan.

### 22.2. Khi hard limit chạm

- **Reject new Encrypt** dưới key đó trước crypto, không tự tăng threshold.
- Bảo đảm mọi service không có đường bypass.
- Không dùng default/hard-coded key hay plaintext fallback.
- Khi key mới sẵn sàng, chuyển new writes đúng version.
- Những in-flight reservations đã cấp có thể cần drain/cancel theo thiết kế; không trả lại slots không chắc chắn.
- Giữ legacy Decrypt nếu policy/cryptoperiod cho phép để đọc dữ liệu cũ.

### 22.3. Khi thấy nonce collision hoặc key usage abuse

- Nếu nghi nonce reuse/raw key compromise, dừng dùng key cho Encrypt mới và kích hoạt incident handling.
- Thu logs, IV allocation evidence, key IDs, material versions, affected objects và producer instances.
- Phân biệt **key usage compromise, key material compromise và data compromise**.
- Nếu raw DEK đã lộ hoặc nonce reuse nguy hiểm, cân nhắc **DEK replacement + re-encrypt**, không chỉ rotate KEK.
- Nếu lộ signing key hoặc signer API bị lạm dụng, đánh giá artifacts, key revocation và trust distribution.
- Nếu chỉ có telemetry gap, ghi **INSUFFICIENT_EVIDENCE**, không kết luận đã xảy ra nonce collision mà chưa có bằng chứng.

### 22.4. Runbook khi nguồn counter không khả dụng

Nếu allocator outage hoặc inconsistent:

1. Không cấp IV mới nếu không chứng minh uniqueness.
2. Không mở một bản counter ước lượng từ dashboard làm nguồn hard stop.
3. Thử failover sang durable source có consistency đã được kiểm định.
4. Nếu nguồn cũ đã bị rollback/uncertain, chuyển **new key material** theo approved emergency workflow khi phù hợp.
5. Audit outage, old key state, authorized operators và key versions.
6. Trước resume, kiểm tra mọi producers đã đồng bộ với trạng thái mới.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Chỉ đếm KMS API, bỏ AES local** | Không thấy DEK usage thực tế | Instrument data plane + KMS |
| **Một count cho mọi operation** | Sai ngưỡng theo thuật toán | Separate by operation/mode |
| **Gom theo alias thay vì key version** | Counter key cũ bị reset khi alias đổi | Immutable material identity |
| **Reset count khi restart** | Cấp lại IV | Durable monotonic state |
| **Counter riêng mỗi pod với cùng nonce prefix** | Trùng (key, IV) | Disjoint IV domains/global allocator |
| **Đếm sau Encrypt rồi enforce hard limit** | Race conditions, over-budget | Reserve atomically trước primitive |
| **Refund nonce khi timeout** | IV có thể được tái cấp | Burn uncertain slots |
| **Idempotency request ID dùng làm IV tùy ý** | IV collision hoặc cross-key confusion | Approved nonce construction riêng |
| **Tin random nonce không cần bound** | Collision risk tăng theo số lượt | Approved limits/monitoring và per-key strategy |
| **Một DEK cho tất cả tenants** | Blast radius lớn, nonce complexity | Scope DEKs theo threat model |
| **Rewrap KEK rồi reset DEK Encrypt count** | Sai cryptographic history | DEK và KEK counters tách |
| **Dùng số business objects thay Encrypt count** | Retry/migration bị bỏ sót | Đo crypto operations thực sự |
| **Chỉ đếm successful Encrypt** | Thiếu reserved slots đã có thể dùng | Reserve/attempt/success riêng |
| **Không đo bytes/blocks** | Bỏ qua usage limits theo data volume | Per-message/total bounds |
| **Đếm Verify thành Sign** | Không thấy thực tế private key usage | Tách Verify/Sign |
| **Đếm Derive calls như distinct subkeys** | Sai blast radius/root usage | Context/subkey registry |
| **Mở rate limit rồi coi là crypto bound** | Key có thể bị overuse qua thời gian | Lifetime budget riêng |
| **Tăng limit để bypass hard stop** | Có thể vi phạm security profile | Rotate key material |
| **Disabling KMS ngăn cả cached DEK** | Local key vẫn dùng được | Cache invalidation + data-plane controls |
| **Usage count thấp nên không review IAM** | Quyền thừa vẫn tồn tại | Access review độc lập |
| **Không tính imported/replicated material** | Tổng usage/nonce namespaces bị chia giả | Logical material family tracking |
| **Backup phục hồi cùng key và counter cũ** | Nonce reuse xuyên lịch sử | Anti-rollback recovery |
| **Tin metrics không có scope/provenance** | Báo PASS khi thiếu regions | Evidence coverage labels |
| **Log raw key để debug counter** | Biến kiểm toán thành key leak | Metadata-only evidence |
| **Xóa key ngay khi đạt limit** | Mất Decrypt/restore dữ liệu cũ | Lifecycle/dependency review |

## 24. Checklist thiết kế key usage count

### Định nghĩa và phân loại

1. Có xác định key class (DEK, KEK, signing, HMAC, root, agreement)?
2. Có định nghĩa algorithm/mode, key size, IV/tag profile và purpose?
3. Counter gắn với immutable key material/version, không chỉ alias?
4. Có phân biệt operation Encrypt/Decrypt/Wrap/Unwrap/Sign/Verify/Derive?
5. Attempts, reservations, completed và denied được đo riêng?
6. Có đối soát cùng raw key material import/replicate ở nhiều nơi?
7. Có ghi source, timestamp, scope, policy version và evidence quality?
8. Không lấy KMS billing count thay AES local Encrypt count?
9. Có phân biệt business success, API requests và crypto invocations?
10. Có tính processed bytes/blocks và message size khi phù hợp?

### Nonce và atomic reservation

11. Có nonce uniqueness invariant dưới cùng AES-GCM key?
12. IV construction tuân theo approved profile/tiêu chuẩn/provider?
13. Random IV có usage bounds phù hợp, không tin vào xác suất thấp vô hạn?
14. Deterministic IV có counter không rollback và domain IDs không trùng?
15. Có **atomic reservation trước Encrypt**?
16. Có hard-stop khi không thể reserve slot?
17. Có ngăn counter wrap-around/integer overflow?
18. Slot bị lỗi/timeout không được cấp lại khi kết quả chưa rõ?
19. Multi-JVM/pod/region có global allocator hoặc disjoint IV domains đáng tin?
20. Restart/failover/backup restore không cấp lại slots?
21. Preallocated ranges được quản lý khi worker crash?
22. Không có crypto path bypass allocator để dùng cùng raw key?

### Lifecycle, IAM và KMS/HSM

23. Usage budget có căn cứ algorithm, key purpose, message bounds và threat model?
24. Có soft alerts đủ sớm để triển khai key mới?
25. Có hard bound độc lập với dashboard/alert?
26. Time-based, count-based và event-based triggers được xét riêng?
27. Key đã hết Encrypt budget được chuyển new-writes sang material mới?
28. Old key còn Decrypt/Verify history theo policy khi cần?
29. KEK rewrap không reset DEK Encrypt counter?
30. Khi DEK đã lộ/nonce reuse, có đánh giá re-encrypt?
31. IAM least privilege giới hạn principal-key-operation-context?
32. Quyền CreateGrant/ChangePolicy và quyền sửa usage budget có SoD?
33. Key custodian/owner/reviewer/auditor có trách nhiệm rõ?
34. KMS/HSM API counts và local DEK counts được phân biệt?
35. Cached DEKs có TTL/invalidation và được xét khi revoke KMS quyền?
36. Key registry lưu version, cryptoperiod, nonce profile và counter scope?
37. Không destroy KEK/DEK khi backups còn phụ thuộc?
38. Có restore test đúng key versions và ciphertext metadata?

### Audit, giám sát và xác minh

39. Có metric reservations/attempts/completed/denied riêng?
40. Có giám sát failed tag/Decrypt/Verify anomalies?
41. Có alerts cho Sign/Unwrap/Derive bất thường theo identity?
42. Audit không chứa raw keys, tokens hoặc plaintext nhạy cảm?
43. Evidence bảo vệ integrity, scope và retention?
44. Có kiểm tra counter mismatch / unexpected rollback?
45. Dashboard nêu rõ incomplete coverage thay vì mặc định PASS?
46. Có runbook khi allocator outage hoặc reached hard limit?
47. Concurrency/restart/failover/nonce collision tests được lên kế hoạch?
48. Có incident handling cho key compromise hoặc nonce reuse?
49. Có đo throughput/usage velocity và time-to-exhaustion?
50. Có quy trình independent review trước tăng budget hoặc thay policy?

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Key usage count là gì? Vì sao một số `usageCount=10000` chưa đủ?

**Đáp án:** Nó đếm các thao tác với khóa theo định nghĩa. Cần biết **key/version, algorithm, operation, attempted/reserved/completed semantics, scope, timeframe và source** trước khi dùng để ra quyết định.

**Câu 2.** KMS ghi 500 lần Unwrap nhưng ứng dụng đã AES-GCM Encrypt 100.000 lần dưới cùng DEK. Số nào liên quan trực tiếp tới nonce usage của DEK?

**Đáp án:** **Số AES-GCM Encrypt/nonce reservations dưới DEK**. Số KMS Unwrap phản ánh việc dùng KEK để lấy DEK, không thay local Encrypt count.

**Câu 3.** Tại sao một AtomicLong trong mỗi pod không đảm bảo nonce duy nhất?

**Đáp án:** Nó chỉ atomic **trong cùng JVM**. Hai pods có thể có cùng prefix/counter hoặc rollback khi restart. Cần global reservation hay IV domains được cấp duy nhất dưới cùng key.

**Câu 4.** Có thể hoàn lại nonce slot khi Encrypt timeout không?

**Đáp án:** Không nên nếu không chứng minh operation chưa xảy ra; slot có thể đã dùng. **Burn slot** bảo thủ hơn tái cấp IV, dù reserved > completed.

**Câu 5.** Một key có cryptoperiod một năm, mới ba tháng nhưng đã đạt usage limit. Có được tiếp tục Encrypt không?

**Đáp án:** Không, nếu policy/cryptographic bound yêu cầu hard stop. Phải chuyển sang **material mới**; time-based deadline không ghi đè count bound.

**Câu 6.** DEK-v1 được rewrap dưới KEK-v2. DEK usage count có reset không?

**Đáp án:** **Không.** DEK bytes không đổi, nên cryptographic Encrypt history không đổi. KEK Wrap/Unwrap count được ghi cho KEK versions riêng.

**Câu 7.** Đếm nhiều Decrypt có nghĩa đang dùng thêm nonce cho AES-GCM Encrypt không?

**Đáp án:** Không. Decrypt dùng IV đã ghi trong ciphertext, nhưng attempts/tag failures vẫn cần theo dõi để phát hiện misuse và đánh giá rủi ro.

**Câu 8.** Số business objects đã lưu có bằng số AES Encrypt không?

**Đáp án:** Không luôn. Một object có thể bị Encrypt lại vì retry, backup, re-encrypt migration; ngược lại một batch có thể bao gồm nhiều objects trong một operation.

**Câu 9.** Khi cùng raw AES key được import vào hai regions, mỗi region có budget riêng được không?

**Đáp án:** **Không thể coi đó là hai key vật liệu độc lập.** Cryptographic usage/nonce uniqueness phải xét toàn bộ nơi dùng cùng raw material.

**Câu 10.** Vì sao không có một ngưỡng key usage chung cho AES-GCM, Ed25519, HMAC và HKDF?

**Đáp án:** Các primitive có **security bounds, nonce/randomness assumptions, message-length constraints và usage semantics khác nhau**. Ngưỡng dựa trên algorithm/profile/threat model, không chỉ số request.

**Câu 11.** Tại sao Sign count của Ed25519 không bằng Verify count?

**Đáp án:** **Sign** dùng private signing key để tạo chữ ký; **Verify** có thể được thực hiện hàng triệu lần bằng public key mà private key không được sử dụng thêm.

**Câu 12.** Count ECDSA Sign có chứng minh nonce ECDSA an toàn không?

**Đáp án:** Không. Lỗi nonce generation/reuse có thể làm lộ private key dù count thấp. Cần provider/implementation và signing profile chính xác.

**Câu 13.** Gọi HKDF 100 lần có nghĩa tạo 100 khóa con khác nhau không?

**Đáp án:** Không. Cùng input/salt/info có thể cho cùng derived key. Cần đếm **distinct derivation contexts/subkeys** khi mục đích yêu cầu.

**Câu 14.** Tại sao soft alert 95% có thể quá muộn?

**Đáp án:** Nếu usage tăng nhanh, thời gian chuẩn bị key mới, cập nhật IAM, chuyển writers và thử restore có thể dài hơn thời gian còn lại. Cần time-to-exhaustion và cảnh báo sớm.

**Câu 15.** Khi counter bị rollback sau restore database, có thể lấy giá trị từ dashboard cộng thêm một lượng dự phòng để tiếp tục không?

**Đáp án:** Không nếu không chứng minh high-watermark thật và uniqueness. Phải **fail closed**, khôi phục allocator có guarantee đúng hoặc chuyển sang **new material**.

**Câu 16.** KMS key non-exportable có ngăn attacker lạm dụng quyền Unwrap không?

**Đáp án:** Không. API có thể trả plaintext DEK theo contract; IAM, monitoring, business authorization và audit vẫn cần thiết.

**Câu 17.** Một workload có quyền Sign nhưng usage count rất thấp; có cần access review không?

**Đáp án:** Có. Quyền tồn tại dù chưa dùng. Một chữ ký trái phép cũng có thể có hậu quả lớn; count và access review bổ sung nhau.

**Câu 18.** Khi Encrypt hard limit đạt, phải destroy key ngay không?

**Đáp án:** Không mặc định. Key có thể cần **Decrypt ciphertext/backup lịch sử**. Chặn new Encrypt, chuyển writers sang key mới và theo dõi dependencies trước destruction.

**Câu 19.** Tại sao không reset counter v1 về 0 sau khi đổi alias sang v2 rồi chuyển lại v1?

**Đáp án:** Vật liệu v1 vẫn mang lịch sử nonce/Encrypt của nó. Reset có thể gây **IV reuse** hoặc vượt giới hạn; ngân sách mới chỉ hợp lý với key material/version mới và profile được duyệt.

**Câu 20.** Thế nào là chương trình key usage count đáng tin?

**Đáp án:** Nó xác định **material/version/operation**, có **hard admission/nonce allocator không cấp trùng và chống rollback**, đo attempts/reservations/successes, bao phủ mọi writers, có IAM và audit bảo vệ, thresholds đúng profile, rotation/recovery runbooks và xử lý ngay khi có compromise.

## 26. Kết luận

**Key usage count không chỉ là số lượt gọi API.** Đây là kiểm soát giúp biết một **key material/version** đã được sử dụng ra sao, còn đáp ứng giới hạn thuật toán và cryptoperiod hay không, có đang bị lạm dụng không và khi nào cần chuyển operations sang key mới.

Đối với **AES-GCM**, điều quan trọng không chỉ là tổng số Encrypt mà là **không dùng lại nonce dưới cùng key**, có **atomic reservation, usage bounds và bảo đảm xuyên instance/region/restart**. KMS có thể ghi số lượt **Wrap/Unwrap của KEK** trong khi các phép **Encrypt dưới DEK** được thực hiện tại ứng dụng; phải đo ở đúng tầng. Với **chữ ký số, HMAC, HKDF và key agreement**, cần các counter và policy khác nhau.

Trong Java, **AtomicLong/LongAdder** có thể minh họa counting và fail-closed limit cho **một process**, nhưng hệ thống production cần **durable, non-rollback distributed allocator hoặc key granularity phù hợp, IAM/KMS/HSM controls, key inventory, audit và rotation/recovery**. Không reset cryptographic history bằng alias change, KEK rewrap hay thao tác sửa dashboard.

**Bộ đếm chỉ có giá trị bảo mật khi nó gắn với đúng vật liệu khóa, đúng phép toán, có thể kiểm chứng và thực sự ngăn việc sử dụng vượt giới hạn trước khi thao tác mật mã xảy ra.**
