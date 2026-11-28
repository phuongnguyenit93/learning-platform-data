# Destroy KEK: Hủy khóa mã hóa khóa an toàn và có kiểm chứng

Một nền tảng lưu hàng triệu hồ sơ đã mã hóa bằng **AES-GCM Data Encryption Key (DEK)**. Mỗi DEK được bảo vệ bằng một **Key Encryption Key (KEK)** trong KMS/HSM. Khi tenant chấm dứt dịch vụ, đội vận hành nhận yêu cầu xóa dữ liệu theo chính sách. Một đề xuất xuất hiện: **gọi DeleteKey cho KEK của tenant** rồi đánh dấu yêu cầu hoàn tất.

Thao tác đó có thể là một phần của **crypto-erasure**, nhưng chỉ khi KEK thực sự là con đường cần thiết duy nhất để mở những DEK tương ứng, mọi bản sao/recovery path đã được kiểm kê, các plaintext DEK không còn trong cache/process, và yêu cầu retention/legal hold đã được xử lý. Nếu một bản backup vẫn chứa KEK, một bản DEK plaintext còn nằm trong memory dump, hoặc DEK đã được wrap bằng một KEK khác, dữ liệu có thể vẫn đọc được.

Ngược lại, nếu doanh nghiệp chỉ muốn **ngừng dùng KEK cũ sau rotation**, destroy ngay có thể làm mất khả năng giải mã archive và backup hợp lệ. Cần rewrap EDK sang KEK mới hoặc có kế hoạch re-encrypt data bằng DEK mới trước khi hủy.

**Destroy KEK** là quyết định loại bỏ khả năng sử dụng một key material khỏi hệ thống và mọi đường phục hồi được kiểm soát. Đây là bước có thể không đảo ngược, ảnh hưởng tới dữ liệu, backup, dịch vụ và nghĩa vụ lưu trữ. Bài này hướng dẫn cách phân biệt **disable, retire, revoke, schedule deletion và destroy**, lập dependency inventory, lựa chọn crypto-erasure hay retirement, tổ chức destruction ceremony, kiểm tra KMS/HSM và lưu bằng chứng.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nội dung kết nối vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy với **key hierarchy, envelope encryption, DEK/KEK, backup/DR, quorum, IAM, audit và compliance**. Mục tiêu là đảm bảo tổ chức chỉ hủy KEK khi đã biết chính xác **điều gì sẽ không thể mở được sau đó**, và có thể chứng minh thao tác đã hoàn thành theo đúng phạm vi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **KEK** trong envelope encryption và mối quan hệ với DEK, EDK, child KEK và backup wrapping key.
2. Phân biệt **disable, suspend, retire, revoke, schedule deletion, destroy và crypto-erasure**.
3. Xác định dữ liệu/phụ thuộc nào sẽ mất khả năng truy cập khi KEK bị hủy.
4. Lập **dependency inventory** cho EDK, backup, archive, replica, escrow, cache, HSM backup và key hierarchy.
5. Phân biệt **retirement after migration** với **intentional crypto-erasure** để chọn điều kiện hủy đúng.
6. Hiểu sự khác nhau giữa **KMS deletion semantics, HSM zeroization, imported key material và provider-managed key**.
7. Thiết kế **approval, quorum, dual control và destruction ceremony** cho KEK nhạy cảm.
8. Đánh giá giới hạn của crypto-erasure khi plaintext DEK, alternative wrapping, backup hoặc attacker copy còn tồn tại.
9. Thiết kế quy trình **dry-run, hold period, cancellation window, final deletion và independent verification**.
10. Viết policy gate bằng **Java 17** để chặn hủy khi dependency inventory chưa đầy đủ, còn legal hold hoặc thiếu approval.

## 2. KEK trong key hierarchy

### 2.1. DEK và KEK làm hai nhiệm vụ khác nhau

- **DEK (Data Encryption Key):** trực tiếp mã hóa nội dung, ví dụ AES-256-GCM cho một record, object hoặc batch.
- **KEK (Key Encryption Key):** bảo vệ DEK bằng Wrap/Unwrap hoặc Encrypt/Decrypt theo cơ chế được thiết kế.
- **EDK (Encrypted Data Key):** DEK đã được wrap/encrypt bằng KEK; EDK có thể được lưu cùng ciphertext.

~~~mermaid
flowchart TD
    P["Plaintext record"] --> D["DEK"]
    D --> E["AES-GCM Encrypt"]
    E --> C["Ciphertext + nonce + tag + AAD"]
    D --> W["Wrap bằng KEK"]
    K["KEK trong KMS/HSM"] --> W
    W --> X["EDK / Wrapped DEK"]
    C --> DB[("Encrypted database")]
    X --> DB
    K --> B["KMS/HSM backup / recovery path"]
~~~

Ứng dụng khi đọc thường lấy EDK và metadata, gọi KMS/HSM để Unwrap DEK, sau đó dùng DEK để xác minh tag và giải mã ciphertext. **KEK có thể non-exportable**, nhưng plaintext DEK có thể xuất hiện trong process nếu API trả DEK cho ứng dụng.

### 2.2. Hủy KEK có thể ảnh hưởng nhiều dữ liệu

Một KEK có thể wrap:

- Nhiều DEK theo từng record/object.
- DEK của nhiều batch dữ liệu.
- Một hoặc nhiều child KEK trong hierarchy.
- Backup wrapping keys hoặc HSM backup objects, tùy thiết kế.
- Key material phục vụ nhiều environment/region nếu tổ chức dùng chung sai phạm vi.

Do đó, **blast radius của KEK** thường lớn hơn một DEK đơn lẻ. Trước khi hủy phải xác định chính xác **key ID/version, tenant, purpose, region, account, partition và tất cả dependency**.

### 2.3. Key hierarchy cần có dependency graph

~~~mermaid
flowchart TD
    R["Recovery root / backup wrapping key"] --> H["HSM backup object"]
    R --> K0["Platform KEK"]
    K0 --> K1["Tenant KEK A"]
    K0 --> K2["Tenant KEK B"]
    K1 --> E1["EDK set A"]
    K2 --> E2["EDK set B"]
    E1 --> D1["DEK A1, A2, A3"]
    E2 --> D2["DEK B1, B2"]
    D1 --> C1["Ciphertext A"]
    D2 --> C2["Ciphertext B"]
~~~

Nếu hủy **Tenant KEK A**, dữ liệu tenant B không nên bị ảnh hưởng. Nếu hủy **Platform KEK**, có thể đồng thời làm mất đường phục hồi Tenant KEK A/B và backup object. **Không chọn key để hủy chỉ bằng tên alias hoặc lastUsedAt**; phải dựa trên dependency graph được đối soát.

### 2.4. Một key có thể có nhiều đường mở

Một EDK có thể được bảo vệ bởi:

- KEK chính trong KMS/HSM.
- KEK dự phòng/DR theo quy trình được phê duyệt.
- Một wrapping key khác sau rewrap.
- Một bản plaintext DEK đã được ứng dụng cache hoặc export.
- Một bản sao backup của KEK hoặc recovery root.

**Hủy một KEK object không chứng minh DEK đã mất khả năng giải mã** nếu bất kỳ đường nào ở trên vẫn còn. Ngược lại, nếu key hierarchy được thiết kế đúng và không có alternative copy, hủy KEK có thể làm các EDK tương ứng không thể Unwrap bằng hệ thống hợp lệ.

## 3. Destroy khác disable, retire và revoke

### 3.1. Các trạng thái và hành động

| Hành động/trạng thái | Ý nghĩa | Có thể đảo ngược? | Tác động điển hình |
|---|---|---|---|
| **ACTIVE** | Được phép dùng theo policy | Có | Encrypt/Wrap hoặc các operations được cấp |
| **DISABLED** | Provider chặn một số hoặc toàn bộ crypto operations | Thường có thể enable lại | Tạm ngừng sử dụng, chưa nhất thiết xóa material |
| **SUSPENDED** | Policy/incident tạm khóa sử dụng | Tùy implementation | Ngăn operations khi điều tra |
| **RETIRED** | Không dùng cho mục đích mới, có thể giữ historical decrypt/unwrap | Thường có | Dữ liệu cũ vẫn có thể cần KEK |
| **REVOKED** | Quyền/certificate/key usage bị rút theo một trust/policy domain | Tùy loại revoke | Không đồng nghĩa raw material bị xóa |
| **PENDING_DELETION** | Đã lên lịch hủy, có thể đang trong waiting period | Có thể hủy lịch tùy provider | Cửa sổ cuối để cancel/restore |
| **DESTROYED** | Material/key object đã bị hủy theo semantics của provider | Thường không | Crypto operations không còn thực hiện được với material đó |

**Tên trạng thái không đồng nhất giữa các KMS/HSM.** Có provider dùng Enabled/Disabled, provider khác có PendingDeletion/Deleted, HSM có thể có lệnh zeroize hoặc destroy object. Phải đọc đúng provider contract và xác minh hiệu lực thực tế.

### 3.2. Disable không phải destroy

Disable KEK có thể ngăn Unwrap mới, nhưng:

- Backup của key vẫn có thể tồn tại.
- Provider có thể cho phép enable lại.
- Plaintext DEK đã được Unwrap vẫn có thể nằm trong JVM/cache.
- Một replica hoặc region khác có thể giữ key object enabled.
- Operator có thể có quyền restore/import key.

Vì vậy, disable hữu ích cho **containment, pause hoặc retirement transition**, nhưng không tự chứng minh crypto-erasure.

### 3.3. Retire không phải destroy

Khi rotation, KEK cũ có thể chuyển sang **read-only/historical Unwrap** để mở EDK cũ, còn KEK mới bảo vệ DEK mới. Trong thời gian archive/backup còn phụ thuộc KEK cũ, hủy nó có thể làm mất dữ liệu hợp lệ.

Retirement thường có mục tiêu:

1. Ngừng Wrap DEK mới bằng KEK cũ.
2. Rewrap EDK sang KEK mới nếu cần.
3. Kiểm kê archive, backup, replicas và legal hold.
4. Xác minh restore end-to-end.
5. Chỉ sau khi không còn dependency cần giữ mới xem xét destroy.

### 3.4. Revoke không tự hủy key material

Từ revoke IAM grant, revoke certificate, revoke key usage policy tới destroy key object là các thao tác khác nhau. Một KMS key có thể vẫn tồn tại sau khi role bị revoke; một certificate bị revoke không tự xóa private key; một KEK bị disable không tự xóa EDK hay plaintext DEK.

### 3.5. Destroy là một quyết định không đảo ngược

Trước khi hủy, cần trả lời:

- Có **data retention/legal hold** nào còn yêu cầu đọc dữ liệu không?
- Có **backup/DR** cần key để phục hồi không?
- Có **child keys hoặc EDKs** còn được phép dùng không?
- Có **recovery shares, escrow, replicas hoặc imported material** không?
- Có plaintext DEK/key handle/cache còn tồn tại không?
- Có **alternative wrapping path** mà tổ chức không biết không?
- Ai đã phê duyệt phạm vi và phương thức hủy?

Nếu câu trả lời chưa rõ, chưa đủ cơ sở để tuyên bố hủy KEK đã hoàn tất.

## 4. Hai mục đích hủy KEK: Retirement và crypto-erasure

### 4.1. Retirement after migration

Mục tiêu là **ngừng phụ thuộc vào KEK cũ nhưng vẫn giữ dữ liệu cần truy cập**. Trước khi destroy:

1. Ngừng tạo EDK mới bằng KEK cũ.
2. Chuyển các EDK cần giữ sang KEK mới bằng **rewrap** hoặc cơ chế migration tương đương.
3. Kiểm tra ciphertext, AAD, wrapping context và key references vẫn hợp lệ.
4. Cập nhật backup/archive/replica theo retention và migration policy.
5. Xác minh không còn DEK/child KEK hợp lệ nào chỉ mở được bằng KEK cũ.
6. Kiểm tra DR restore bằng key hierarchy mới.
7. Chỉ sau khi dependency inventory về zero trong phạm vi phải giữ mới destroy KEK cũ.

~~~mermaid
flowchart TD
    A["KEK-v1 ACTIVE"] --> B["Ngừng Wrap mới bằng v1"]
    B --> C["KEK-v2 ACTIVE"]
    C --> D["Rewrap EDK cần giữ: v1 -> v2"]
    D --> E["Kiểm tra primary, archive, backup, replica"]
    E --> F{"Còn dependency hợp lệ của v1?"}
    F -->|"Có"| G["Giữ v1 RETIRED, tiếp tục migration"]
    G --> E
    F -->|"Không"| H["Restore drill + approval"]
    H --> I["Destroy KEK-v1"]
~~~

### 4.2. Intentional crypto-erasure

Mục tiêu là **làm cho dữ liệu trong một phạm vi xác định không thể truy cập bằng cách hủy key material cần thiết**. Ví dụ, tenant đã hết retention, tổ chức được phép xóa dữ liệu và muốn loại bỏ DEK/KEK theo một thiết kế crypto-erasure.

Trước khi destroy cần xác minh:

- Tất cả ciphertext thuộc scope đã được xác định.
- Tất cả EDK cần bị vô hiệu hóa thực sự phụ thuộc vào KEK này.
- Không còn alternative wrapping key, recovery copy, escrow hoặc replica có thể mở EDK.
- Không còn plaintext DEK trong cache, process, dump, backup hay thiết bị.
- Không còn legal hold hoặc nghĩa vụ lưu giữ xung đột.
- Các bản copy dữ liệu và key nằm ngoài hệ thống đã được tính tới.
- Đã phê duyệt **phạm vi xóa và mức đảm bảo**; không tuyên bố rộng hơn bằng chứng.

**Crypto-erasure không phải một lệnh DeleteKey đơn lẻ**. Đây là một quy trình dữ liệu và key lifecycle đồng bộ.

### 4.3. Chọn đúng mục đích trước khi lập kế hoạch

| Câu hỏi | Retirement after migration | Intentional crypto-erasure |
|---|---|---|
| Có cần đọc dữ liệu sau hành động? | **Có** | Theo mục tiêu, dữ liệu trong scope sẽ không thể đọc |
| Có cần rewrap EDK sang KEK khác? | Thường có | Không nếu EDK nằm trong scope bị xóa; có thể có với dữ liệu ngoài scope |
| Có được giữ backup phục hồi dữ liệu? | Có thể, nếu retention yêu cầu | Không được giữ đường mở dữ liệu trong scope nếu mục tiêu là crypto-erasure |
| Cần inventory? | Có | **Bắt buộc và phạm vi chặt hơn** |
| Có thể hủy nếu còn legal hold? | Không | Không |
| Bằng chứng chính | Không còn dependency cần giữ; DR mới thành công | Không còn key path hợp lệ ngoài scope và deletion đã hoàn tất theo provider |

### 4.4. Một yêu cầu có thể chứa hai scope

Ví dụ tenant đóng dịch vụ nhưng có:

- **Invoice records** phải giữ theo thời hạn lưu trữ.
- **Temporary session data** được phép xóa ngay.
- **Fraud investigation records** đang có legal hold.

Không thể destroy một KEK chung cho cả ba nhóm nếu nó làm invoice và legal-hold records không thể đọc. Có thể cần **tách KEK theo data class/retention scope**, rewrap dữ liệu phải giữ và chỉ crypto-erase key hierarchy riêng của temporary data.

## 5. Dependency inventory trước khi hủy

### 5.1. Phải tìm tất cả nơi có thể giữ hoặc mở key

Một inventory đầy đủ không chỉ là query EDK trong primary database. Cần rà soát:

1. **KMS key object:** key ID/version, account/project, region, partition, state, key purpose, aliases.
2. **EDK trong primary data store:** database, object storage, message payload, search index và caches.
3. **DEK/child KEK:** key hierarchy có child keys được wrap bằng target KEK hay không.
4. **Backup/restore:** HSM backup blob, snapshots, database backups, offline tapes, recovery media.
5. **Replica/multi-region:** key replicas, cross-region copies, DR accounts, failover clusters.
6. **Escrow/recovery:** recovery shares, split knowledge, escrow agent, break-glass package và quorum tokens.
7. **Application memory:** plaintext DEK caches, process memory, sidecar, local agent, JVM heap, swap/core dump.
8. **Export/import:** raw material từng được export, BYOK source files, import wrapping packages, staging locations.
9. **External consumers:** partner systems, offline archives, data exports và downstream pipelines.
10. **Operational artifacts:** logs, debug dumps, crash reports, support bundles, temporary files và CI artifacts.
11. **Alternative wrappers:** EDK đã được rewrap dưới KEK khác, duplicate wrapped DEK hoặc backup key version.
12. **Provider-managed recovery:** provider backup, key version retention, deletion waiting period và recovery options.

Không phải mọi mục đều có thể quan sát tự động. Phải ghi **nguồn evidence, owner, thời điểm kiểm kê và giới hạn quan sát**.

### 5.2. Bảng dependency inventory mẫu

| Dependency | Câu hỏi cần trả lời | Bằng chứng cần có |
|---|---|---|
| **EDK references** | Bao nhiêu EDK đang wrap bằng keyRef/version này? | Query theo immutable key ID/version, counts và sample |
| **Child KEKs** | Có key nào đang được wrap bởi KEK này? | Key hierarchy registry và provider metadata |
| **Backups** | Backup nào cần KEK để restore? | Backup catalog, manifest, restore tests |
| **Replicas** | Region/account nào còn key object hoặc material? | Provider inventory, replication status |
| **Escrow/shares** | Có recovery path nào có thể tái tạo key? | Custody records, share-set inventory |
| **Plaintext DEK cache** | Process nào còn giữ DEK đã Unwrap? | Cache lease metrics, workload inventory, shutdown evidence |
| **Imported/exported material** | Có raw key copy ngoài KMS/HSM? | BYOK/import records, secret scanning, forensics |
| **External copies** | Partner/archive nào giữ EDK hoặc DEK? | Data lineage, contract, partner confirmation |
| **Legal hold** | Có data scope phải giữ khả năng đọc? | Legal/compliance approval |
| **Provider deletion** | Lệnh hủy có pending window hoặc backup retention? | Provider API status và documentation |

### 5.3. Inventory phải gắn với immutable identity

Không truy dependency chỉ theo alias **tenant-kek-current**. Alias có thể đổi từ v4 sang v5, trong khi ciphertext lịch sử vẫn tham chiếu v4.

Mỗi entry nên xác định:

- Provider/account/region/partition.
- **Immutable key ID và material version** (nếu provider expose).
- Purpose, algorithm, owner, tenant/environment.
- Key state và effective time.
- Parent/child relationship.
- Dependency object ID, storage location và retention class.
- Backup/replica/escrow identifiers.

Nếu provider dùng opaque ciphertext blob và tự quản lý material versions, lưu **provider reference/blob semantics** theo contract thay vì tự suy version từ alias.

### 5.4. Thiếu dữ liệu inventory phải fail closed

Nếu một archive không thể xác định key version, hoặc một backup catalog không trả lời được nó có chứa EDK dưới KEK nào, không thể kết luận **zero dependencies**.

Phải:

1. Đặt dependency ở trạng thái **UNKNOWN**, không tự coi là zero.
2. Tìm evidence từ backup manifest, provider audit, data lineage và owner.
3. Cô lập thao tác destroy trong khi scope chưa được xác nhận.
4. Nếu không thể khôi phục evidence, ghi rõ **uncertainty và risk acceptance** theo governance; không báo crypto-erasure đã được chứng minh.

### 5.5. Không nhầm số lượng EDK với số lượng dữ liệu

Một record có thể chứa nhiều EDK do rewrap/rotation. Một EDK có thể bảo vệ DEK mã hóa nhiều objects. Một DEK có thể đã được copy ra ngoài EDK. Vì vậy:

- **EDK count = 0** không tự chứng minh không còn plaintext DEK/ciphertext.
- **EDK count > 0** có thể là dependency cần giữ hoặc dependency chủ đích bị crypto-erase.
- Cần map **EDK → DEK → ciphertext/data scope** và alternative wrappers.
- Counts cần có **snapshot time, query coverage, pagination completeness và source-of-truth**.

## 6. Crypto-erasure: Hiệu lực và giới hạn

### 6.1. Điều kiện để hủy KEK làm mất khả năng mở EDK

Trong mô hình đơn giản:

\[
EDK = Wrap(KEK, DEK)
\]

Nếu KEK material thực sự bị hủy và không có bản sao/recovery path, không thể thực hiện Unwrap EDK bằng KEK đó. Nếu EDK là con đường duy nhất để lấy DEK, ciphertext tương ứng có thể trở nên không thể giải mã bằng hệ thống hợp lệ.

Nhưng kết luận này phụ thuộc vào các điều kiện:

1. KEK là **material đúng** đã wrap DEK trong scope.
2. Không còn backup/replica/escrow/imported copy có thể phục hồi KEK.
3. Không có alternative KEK hoặc EDK copy đã rewrap.
4. Không còn plaintext DEK ở memory/cache/process/export.
5. Không có một key khác được dùng trực tiếp để Encrypt nội dung.
6. Provider đã hoàn tất deletion theo semantics được cam kết.
7. Mọi hệ thống được tính vào scope, kể cả external copies mà tổ chức kiểm soát.

### 6.2. Hủy KEK không xóa ciphertext

Crypto-erasure thường làm **mất khả năng giải mã**, không nhất thiết xóa các byte ciphertext:

- Database row vẫn tồn tại.
- Object storage vẫn có thể giữ file encrypted.
- Backup có thể còn ciphertext và EDK.
- Log có thể còn metadata hoặc thậm chí plaintext nếu ứng dụng từng ghi sai.

Do đó, nếu yêu cầu là **xóa dữ liệu khỏi storage**, có thể còn cần lifecycle deletion cho ciphertext, backups và replicas theo policy. **Crypto-erasure và storage deletion là hai controls khác nhau**, có thể bổ trợ nhưng không thay thế hoàn toàn nhau.

### 6.3. Plaintext DEK đã được mở là một đường bypass

Sau khi Unwrap:

~~~text
KMS/HSM: Unwrap(KEK, EDK) -> plaintext DEK
                                  |
                                  v
                            Application RAM
                                  |
                       +----------+----------+
                       |                     |
                    Decrypt              Cache/Export
                       |                     |
                  Plaintext              DEK copy
~~~

Nếu DEK đã nằm trong memory dump, cache, swap, crash report hoặc một hệ thống khác, destroy KEK không xóa bản DEK đó. Cần:

- Dừng hoặc drain workloads đã Unwrap DEK.
- Thu hồi session/grants và chờ/kiểm tra cache leases hết hạn theo policy.
- Kiểm soát heap dump, core dump, swap, telemetry và temporary files.
- Xác minh không có plaintext DEK export ngoài boundary.
- Xem xét data re-encryption hoặc incident response nếu có dấu hiệu key exposure.

**Không tuyên bố crypto-erasure tuyệt đối chỉ dựa trên việc KMS DeleteKey thành công** nếu không kiểm soát được plaintext DEK copies.

### 6.4. Attacker đã sao chép dữ liệu trước thời điểm hủy

Nếu attacker có **ciphertext + plaintext DEK** trước khi hủy KEK, họ vẫn có thể giải mã bản sao ciphertext đã lấy. Nếu attacker có ciphertext và bản copy KEK/backup có thể restore, họ cũng có thể giữ khả năng giải mã.

Crypto-erasure bảo vệ dữ liệu khỏi **khả năng truy cập trong tương lai qua các key paths đã bị loại bỏ**; nó không thể thu hồi plaintext hoặc key material mà đối thủ đã sao chép.

### 6.5. Crypto-erasure không thay thế retention/legal hold

Trước khi hủy KEK, phải xác định dữ liệu có:

- Thời hạn lưu theo hợp đồng hoặc pháp luật.
- Legal hold, investigation hoặc e-discovery.
- Nghĩa vụ lưu trữ audit, chứng từ, chữ ký số.
- Yêu cầu phục hồi DR trong một khoảng thời gian.

Nếu dữ liệu phải giữ khả năng đọc, crypto-erasure làm mất khả năng thực hiện nghĩa vụ đó. **Approval của data owner không thay thế quyết định legal/compliance khi có hold**.

### 6.6. Mức đảm bảo nên được phát biểu chính xác

Thay vì nói **“mọi bản sao dữ liệu đã bị xóa vĩnh viễn”**, evidence có thể chỉ chứng minh:

- Target KEK object đã chuyển sang trạng thái DESTROYED theo provider.
- Provider không còn hỗ trợ crypto operations với key material đó.
- Các EDK trong inventory scope không còn Unwrap được bằng đường chính.
- Các backup/replicas được quản lý đã được xử lý theo retention.
- Các workloads có thể giữ plaintext DEK đã được dừng hoặc hết lease.

Nêu rõ **phạm vi và giới hạn quan sát** để tránh tuyên bố vượt quá bằng chứng.

## 7. Rewrap và re-encrypt trước khi destroy

### 7.1. Rewrap EDK: Đổi KEK, giữ DEK

Nếu mục tiêu là retire KEK-v1 nhưng vẫn cần đọc dữ liệu:

~~~text
DEK = Unwrap(KEK-v1, EDK-v1, wrapContext-v1)
EDK-v2 = Wrap(KEK-v2, DEK, wrapContext-v2)

Content ciphertext: không đổi
Content DEK: không đổi
Content nonce/tag/AAD: giữ nguyên nếu content format không đổi
Wrapping metadata: cập nhật theo KEK-v2
~~~

Nếu provider hỗ trợ server-side rewrap/reencrypt, ưu tiên đánh giá đường **không trả plaintext DEK về ứng dụng**. Không phải mọi KMS đều hỗ trợ rewrap giữa mọi provider/key type hoặc mọi format EDK.

### 7.2. Re-encrypt content: Đổi cả DEK

Nếu mục tiêu là loại bỏ DEK-v1 hoặc dữ liệu cần được bảo vệ lại:

~~~text
plaintext = Decrypt(DEK-v1, ciphertext-v1, nonce-v1, aad-v1)
DEK-v2 = GenerateDataKey()
ciphertext-v2 = Encrypt(DEK-v2, plaintext, nonce-v2, aad-v2)
EDK-v2 = Wrap(KEK-v2, DEK-v2, context-v2)

Persist new envelope atomically
~~~

Re-encrypt thay đổi **ciphertext, nonce, tag, DEK reference và EDK**. Phải dùng nonce mới theo thuật toán và quản lý transaction/version để không ghi đè dữ liệu cập nhật mới.

### 7.3. So sánh hai phương án

| Đặc điểm | Rewrap | Re-encrypt |
|---|---|---|
| Thay KEK wrapping layer | Có | Có thể có |
| Thay DEK | **Không** | **Có** |
| Thay content ciphertext | Thường không | Có |
| Cần đọc plaintext content | Không nhất thiết nếu provider rewrap server-side | Có trong crypto boundary |
| Giải quyết DEK compromise | **Không** | Có thể, nếu plaintext/backup exposure đã được xử lý |
| Chi phí | Thường thấp hơn | Thường cao hơn |
| Dùng khi | KEK rotation/retirement, DEK vẫn đáng tin | DEK rotation/compromise hoặc thay data encryption |

**Rewrap không chữa được DEK compromise**. **Re-encrypt không thu hồi được plaintext đã bị attacker sao chép trước đó**.

### 7.4. Atomic migration và concurrency

Khi migrate nhiều records, phải tránh:

~~~text
Worker A đọc record revision 12 dưới KEK-v1.
Writer B cập nhật record revision 13 dưới KEK-v2.
Worker A ghi lại envelope từ revision 12.

=> Có thể mất update của Writer B.
~~~

Dùng **compare-and-swap (CAS), ETag hoặc transaction**:

~~~sql
-- Pseudo SQL; schema thực tế có thể khác.
UPDATE encrypted_record
SET envelope_blob = :new_envelope,
    revision = revision + 1
WHERE record_id = :record_id
  AND revision = :expected_revision
  AND kek_ref = :expected_old_kek_ref;
~~~

Nếu update không ảnh hưởng hàng nào, record đã thay đổi; worker phải reload và đánh giá lại. Không được overwrite bằng envelope cũ.

### 7.5. Không destroy trước khi kiểm tra backup

Sau khi primary DB đã rewrap, backup cũ có thể vẫn chứa EDK dưới KEK-v1. Có hai lựa chọn:

1. **Giữ KEK-v1** đến khi backup hết retention hoặc được migrate theo policy.
2. **Tạo backup mới** theo KEK-v2, xác minh restore, rồi xử lý backup cũ đúng retention/destruction rules.

Chỉ khi tất cả bản sao cần giữ đã có recovery path hợp lệ dưới hierarchy mới mới có thể xem xét destroy v1 trong mục tiêu retirement.

## 8. KMS/HSM deletion semantics

### 8.1. Một API Delete không mô tả đầy đủ quá trình hủy

Tùy provider, lifecycle có thể gồm:

~~~text
ACTIVE
  -> DISABLED
  -> SCHEDULED_FOR_DELETION / PENDING_DELETION
  -> WAITING PERIOD
  -> FINAL DELETION / DESTROYED
~~~

Một số HSM có lệnh **zeroize** cho thiết bị/partition và có thể ảnh hưởng nhiều objects; một số HSM hỗ trợ destroy từng key object. KMS cloud có thể có **pending deletion window**, **cancellation**, automatic rotation hoặc provider-managed backup semantics. Không áp dụng một timeline chung cho mọi nền tảng.

### 8.2. Những câu hỏi phải xác minh theo provider

| Câu hỏi | Vì sao quan trọng |
|---|---|
| Delete có **disable ngay** hay key vẫn dùng được trong waiting period? | Xác định thời điểm operations dừng |
| Có thể **cancel deletion** đến thời điểm nào? | Cửa sổ phục hồi khi phát hiện nhầm |
| Final deletion có xóa **mọi material version** không? | Automatic rotation có thể giữ versions lịch sử |
| Có **replica/multi-region copy** cần xóa riêng không? | Một region khác có thể còn khả năng crypto |
| Provider có **backup/escrow** riêng không? | Delete API có thể không mô tả backup retention |
| Imported key material có lifecycle khác provider-generated key không? | Có thể chỉ xóa material import hoặc key object |
| HSM backup blob có thể restore lại object không? | Xóa object không đồng nghĩa xóa backup |
| Có deletion waiting period hoặc legal hold của provider không? | Xác định effective deletion time |
| Có audit event cho scheduled/final deletion không? | Cần bằng chứng vận hành |
| Có thể lấy trạng thái final từ API/attestation nào? | Phân biệt request accepted với deletion complete |

### 8.3. Provider-managed KMS key và imported key material

**Provider-generated key:** KMS thường kiểm soát quá trình tạo và lifecycle của material. Customer có thể chỉ nhìn thấy key resource và trạng thái API. Cần hiểu provider cam kết gì về backup, replication, deletion và retention.

**Imported/BYOK material:** Customer có thể giữ bản nguồn hoặc import package. Xóa key object khỏi KMS chưa chắc xóa file nguồn, offline copy, import wrapping key hay bản sao trong hệ thống staging. Cần quản lý toàn bộ nguồn material.

**External key store:** KMS có thể chỉ giữ reference tới HSM/external key manager. Delete reference trong KMS không nhất thiết destroy key ở external store; phải xử lý cả hai control planes.

### 8.4. HSM zeroization và key object destruction

Phân biệt:

- **Destroy key object:** hủy một object/material theo HSM API.
- **Zeroize partition/device:** xóa nhiều key objects/configuration hoặc đưa thiết bị về trạng thái không còn secret, theo semantics của sản phẩm.
- **Destroy backup blob:** xử lý bản backup theo quy trình riêng.
- **Destroy recovery shares:** loại bỏ các shares/activation credentials có thể tái tạo recovery key.

Zeroize nhầm HSM partition có thể làm mất nhiều keys ngoài scope; destroy một key object nhưng giữ backup blob có thể vẫn phục hồi được key. Cần xác minh **object ID, partition, domain, backup dependencies và blast radius** trước lệnh.

### 8.5. Deletion waiting period

Một cửa sổ chờ có thể giúp:

- Phát hiện nhầm key ID, nhầm tenant hoặc nhầm environment.
- Cho data owner/legal/compliance rà soát dependency.
- Kiểm tra migration/backup/restore evidence.
- Cancel request nếu phát hiện hệ thống vẫn cần key.

Nhưng **pending deletion không phải destroyed**. Nếu provider vẫn cho crypto operations trong thời gian chờ, cần quyết định disable ngay hoặc giới hạn IAM. Nếu provider disable ngay, service có thể mất khả năng đọc trước khi final deletion. Cần hiểu cả hai thời điểm.

### 8.6. Không nhầm deletion confirmation với proof of erasure toàn hệ thống

Provider có thể xác nhận **key resource đã bị deleted** theo contract. Điều đó không tự chứng minh:

- Mọi raw export đã bị xóa.
- Mọi HSM backup blob đã bị destroy.
- Mọi replica/region đã hết material.
- Mọi process đã bỏ plaintext DEK.
- Mọi ciphertext đã bị xóa khỏi storage.
- Attacker không giữ bản sao trước đó.

Biên bản phải ghi rõ **provider deletion evidence** và **system-wide dependency evidence** là hai lớp khác nhau.

## 9. Destruction ceremony: Quy trình hủy KEK có kiểm soát

### 9.1. Trước khi mở ceremony

Yêu cầu destroy phải có:

- **KeyRef chính xác:** provider, account/project, region, partition, key ID/version, tenant và purpose.
- **Mục đích:** retirement after migration hay intentional crypto-erasure.
- **Scope dữ liệu:** record/object/batch/tenant, backup/archive và retention class.
- **Dependency report:** EDKs, child keys, replicas, backup, escrow, cache, imported/exported material.
- **Legal/compliance approval:** xác nhận không có hold/nghĩa vụ xung đột.
- **Migration/restore evidence:** khi retirement, chứng minh dữ liệu cần giữ đã có đường mở mới.
- **Provider deletion plan:** disable, waiting period, cancel window, final deletion và verification method.
- **Quorum/SoD:** requester, key owner, approvers, operator và auditor.
- **Rollback/recovery limitation:** ghi rõ thời điểm sau đó không còn khả năng phục hồi.

### 9.2. Ceremony theo từng giai đoạn

~~~mermaid
sequenceDiagram
    participant O as Key Owner
    participant S as Security/Compliance
    participant A as Independent Approvers
    participant OP as KMS/HSM Operator
    participant P as Provider KMS/HSM
    participant AU as Auditor
    O->>S: Submit destroy request + dependency scope
    S->>S: Review crypto-erasure/retirement, retention, risk
    S->>A: Request approval bound to keyRef + action
    A-->>S: M-of-N approvals / dual control
    S->>OP: Authorize exact destroy operation
    OP->>P: Disable / schedule deletion
    P-->>OP: Pending state + effective time
    OP->>AU: Record provider request and audit reference
    Note over O,AU: Wait/review window if provider supports it
    OP->>P: Finalize destruction after approval window
    P-->>OP: Final deletion result
    OP->>AU: Evidence, status, scope, timestamp
    AU->>AU: Independent verification and closeout
~~~

### 9.3. Checklist tại thời điểm thực hiện

1. Hai người độc lập xác minh **key ID/version và environment** trên provider console/API.
2. Đối chiếu keyRef với approved request và dependency report.
3. Kiểm tra **key state, aliases, grants, parent/child relationship và provider region**.
4. Xác minh đúng mục đích **retirement** hoặc **crypto-erasure**.
5. Xác nhận không có legal hold, retention conflict hoặc incident response đang yêu cầu giữ evidence.
6. Đạt quorum/dual control đúng **action DESTROY**, không tái sử dụng approval cho DISABLE hoặc EXPORT.
7. Thực hiện disable/schedule deletion theo provider semantics.
8. Trong waiting period, kiểm tra alert, migration status, restore dependencies và cancellation request.
9. Finalize destruction đúng key object và ghi provider request ID/result.
10. Kiểm tra key không còn khả năng thực hiện crypto operations theo provider contract.
11. Đối soát replica/backup/import/export/recovery shares và temporary grants.
12. Auditor độc lập xác minh evidence và cập nhật destruction register.

### 9.4. Dual control cho thao tác destroy

Không để một người vừa:

- Chọn key ID và tự khai scope.
- Tự xác nhận dependency inventory.
- Tự phê duyệt legal/retention.
- Tự gọi DeleteKey.
- Tự xác nhận deletion thành công.
- Tự sửa/xóa audit.

Tối thiểu cần tách **requester, approver và executor** theo mức criticality; với KEK root/production, thêm independent witness/auditor và quorum theo policy.

### 9.5. Hủy nhầm key: Vì sao cần dry-run

Một dry-run cần hiển thị:

- Key ID/version đầy đủ và provider scope.
- Alias trỏ tới key nào tại thời điểm kiểm tra.
- Số EDK/dependencies theo từng storage.
- Backup/replica/escrow state.
- Child key relationships.
- Legal hold/retention decision.
- Dữ liệu sẽ mất khả năng truy cập hoặc sẽ được rewrap.
- Key nào không nằm trong scope và phải tiếp tục hoạt động.

**Không chạy wildcard deletion theo alias prefix** hoặc chọn key bằng substring. Trước thao tác final, kiểm tra lại target key trên provider vì alias có thể đã đổi.

## 10. Quyết định Destroy: Policy gate

### 10.1. Điều kiện chung

Một KEK chỉ nên qua policy gate khi:

1. Key identity/version xác định duy nhất.
2. Key không còn được dùng để Wrap mới.
3. Owner và security approvers xác nhận mục đích.
4. Dependency inventory hoàn tất và có evidence.
5. Legal hold/retention không ngăn hành động.
6. Recovery/backup/replica/escrow đã được xử lý đúng intent.
7. Plaintext DEK caches và workloads được đánh giá.
8. Quorum/dual control đã đạt.
9. Provider semantics/waiting period được xác minh.
10. Destruction audit được lưu ở hệ thống độc lập.

### 10.2. Gate riêng cho retirement

**RETIRE_AFTER_MIGRATION** yêu cầu:

- Không còn EDK/child key cần giữ chỉ được wrap bởi target KEK.
- Tất cả EDK cần giữ đã rewrap hoặc data đã re-encrypt.
- Backup/archive/replica cần giữ đã có recovery path dưới hierarchy mới.
- Restore drill thành công.
- Không còn active grants/workloads cần target key.
- Không còn cache lease hoặc plaintext DEK dependency cần target key.

### 10.3. Gate riêng cho crypto-erasure

**CRYPTO_ERASURE** có mục tiêu khác: EDK trong scope có thể vẫn tồn tại, nhưng chúng phải **không còn đường mở hợp lệ** sau khi target KEK bị destroy. Gate cần:

- Scope dữ liệu/EDK được phê duyệt rõ.
- Không có alternative KEK/wrapping path cho DEK trong scope.
- Không có recovery backup/escrow/replica có thể tái tạo target KEK.
- Không có plaintext DEK cache/copy trong hệ thống được quản lý.
- Không có legal hold hoặc retention obligation.
- Ciphertext/EDK ngoài scope không bị ảnh hưởng.
- Provider deletion hoàn tất và có evidence.

**Không được dùng gate retirement cho crypto-erasure hoặc ngược lại**: retirement cần giữ dữ liệu đọc được; crypto-erasure cố ý làm dữ liệu trong scope không thể mở.

### 10.4. Gate có thể trả về bốn trạng thái

| Decision | Ý nghĩa | Hành động |
|---|---|---|
| **ALLOW_SCHEDULE** | Đủ điều kiện bắt đầu pending deletion | Schedule và theo dõi waiting period |
| **ALLOW_FINALIZE** | Đã hết hold window, không phát hiện blocker | Finalize theo approval |
| **DENY** | Có blocker rõ ràng | Không hủy, xử lý blocker |
| **UNKNOWN / INCOMPLETE** | Thiếu evidence hoặc dependency không xác định | Fail closed, bổ sung inventory |

Không diễn giải **UNKNOWN** thành **ALLOW**. Một dependency không biết là một dependency chưa được giải quyết.

## 11. Java 17: Policy gate trước khi destroy KEK

Ví dụ sau mô phỏng **quyết định policy**, không gọi KMS/HSM và không chứa key material. Nó phân biệt:

- **RETIRE_AFTER_MIGRATION:** không còn dependency cần giữ dưới KEK cũ.
- **CRYPTO_ERASURE:** EDK còn tồn tại có thể được chấp nhận nếu tất cả đều nằm trong scope crypto-erasure đã phê duyệt và không còn alternative key path.
- **UNKNOWN/INCOMPLETE:** inventory thiếu, có plaintext DEK cache/copy, backup/replica/escrow hoặc child key chưa xử lý.
- **Quorum và dual control:** owner/security approvals, quorum, independent auditor, temporary grants đã thu hồi.
- **Pending deletion:** chỉ finalize khi hold window đã qua và inventory được revalidate.

Trong ví dụ, số lượng provider backup được tính là **các bản sao có thể restore độc lập mà không được bao phủ bởi cam kết final deletion của provider**. Nếu provider có backup nội bộ và contract nói rõ chúng bị loại bỏ theo final deletion, phải ghi nhận semantics/evidence đó trong inventory thay vì tự suy đoán.

~~~java
import java.util.Objects;

public final class DestroyKekGateDemo {

    enum Intent {
        RETIRE_AFTER_MIGRATION,
        CRYPTO_ERASURE
    }

    enum KeyState {
        ACTIVE,
        DISABLED,
        RETIRED,
        PENDING_DELETION,
        DESTROYED
    }

    enum Phase {
        SCHEDULE,
        FINALIZE
    }

    record KeyRef(
            String provider,
            String account,
            String region,
            String keyId,
            int version,
            String tenant,
            String purpose) {
        KeyRef {
            Objects.requireNonNull(provider);
            Objects.requireNonNull(account);
            Objects.requireNonNull(region);
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(purpose);
            if (provider.isBlank() || account.isBlank()
                    || region.isBlank() || keyId.isBlank()
                    || tenant.isBlank() || purpose.isBlank()
                    || version < 1) {
                throw new IllegalArgumentException("Invalid key identity");
            }
        }
    }

    record Inventory(
            boolean complete,
            int edkReferences,
            int edkReferencesOutsideErasureScope,
            int unresolvedChildKeys,
            int providerBackupCopies,
            int replicaCopies,
            int escrowCopies,
            int alternativeWrapPaths,
            int plaintextDekCaches,
            int knownExternalPlaintextCopies,
            boolean noLegalHold,
            boolean retentionSatisfied,
            boolean allEdksInApprovedErasureScope,
            boolean noNewWrapOperations,
            boolean temporaryGrantsRevoked,
            boolean dryRunPassed,
            boolean inventoryRevalidated,
            boolean noNewDependenciesDuringWindow) {

        Inventory {
            if (edkReferences < 0
                    || edkReferencesOutsideErasureScope < 0
                    || unresolvedChildKeys < 0
                    || providerBackupCopies < 0
                    || replicaCopies < 0
                    || escrowCopies < 0
                    || alternativeWrapPaths < 0
                    || plaintextDekCaches < 0
                    || knownExternalPlaintextCopies < 0
                    || edkReferencesOutsideErasureScope > edkReferences) {
                throw new IllegalArgumentException(
                        "Invalid dependency inventory");
            }
        }
    }

    record Approval(
            boolean targetConfirmedAsKek,
            boolean keyOwnerApproved,
            boolean securityApproved,
            boolean quorumReached,
            boolean independentAuditorAssigned,
            boolean scopeApproved,
            boolean providerSemanticsConfirmed) {}

    record Request(
            KeyRef target,
            Intent intent,
            Phase phase,
            KeyState keyState,
            Inventory inventory,
            Approval approval,
            boolean waitingPeriodElapsed) {

        Request {
            Objects.requireNonNull(target);
            Objects.requireNonNull(intent);
            Objects.requireNonNull(phase);
            Objects.requireNonNull(keyState);
            Objects.requireNonNull(inventory);
            Objects.requireNonNull(approval);
        }
    }

    record Decision(boolean allowed, String reason) {}

    private static Decision deny(String reason) {
        return new Decision(false, reason);
    }

    static Decision evaluate(Request request) {
        Inventory i = request.inventory();
        Approval a = request.approval();

        if (!i.complete()) {
            return deny("INVENTORY_INCOMPLETE");
        }
        if (!i.noLegalHold() || !i.retentionSatisfied()) {
            return deny("LEGAL_OR_RETENTION_BLOCKER");
        }
        if (!a.targetConfirmedAsKek()) {
            return deny("TARGET_NOT_CONFIRMED_AS_KEK");
        }
        if (!a.scopeApproved() || !a.keyOwnerApproved()
                || !a.securityApproved() || !a.quorumReached()
                || !a.independentAuditorAssigned()) {
            return deny("APPROVAL_OR_QUORUM_MISSING");
        }
        if (!a.providerSemanticsConfirmed()) {
            return deny("PROVIDER_SEMANTICS_UNKNOWN");
        }
        if (!i.noNewWrapOperations()) {
            return deny("KEY_STILL_USED_FOR_NEW_WRAP");
        }
        if (!i.temporaryGrantsRevoked()) {
            return deny("TEMPORARY_GRANTS_STILL_ACTIVE");
        }
        if (!i.dryRunPassed()) {
            return deny("DRY_RUN_NOT_PASSED");
        }
        if (i.unresolvedChildKeys() != 0) {
            return deny("CHILD_KEY_DEPENDENCY_REMAINS");
        }
        if (i.plaintextDekCaches() != 0
                || i.knownExternalPlaintextCopies() != 0) {
            return deny("PLAINTEXT_DEK_COPY_OR_CACHE_REMAINS");
        }

        if (request.phase() == Phase.SCHEDULE) {
            if (request.keyState() != KeyState.DISABLED
                    && request.keyState() != KeyState.RETIRED) {
                return deny("KEY_MUST_BE_DISABLED_OR_RETIRED");
            }
        } else {
            if (request.keyState() != KeyState.PENDING_DELETION) {
                return deny("KEY_NOT_PENDING_DELETION");
            }
            if (!request.waitingPeriodElapsed()) {
                return deny("WAITING_PERIOD_NOT_ELAPSED");
            }
            if (!i.inventoryRevalidated()
                    || !i.noNewDependenciesDuringWindow()) {
                return deny("FINAL_REVALIDATION_FAILED");
            }
        }

        if (i.providerBackupCopies() != 0
                || i.replicaCopies() != 0
                || i.escrowCopies() != 0
                || i.alternativeWrapPaths() != 0) {
            return deny("RECOVERY_OR_ALTERNATIVE_KEY_PATH_REMAINS");
        }

        if (request.intent() == Intent.RETIRE_AFTER_MIGRATION) {
            if (i.edkReferences() != 0) {
                return deny("EDK_DEPENDENCY_REMAINS_FOR_RETIREMENT");
            }
        } else {
            if (!i.allEdksInApprovedErasureScope()
                    || i.edkReferencesOutsideErasureScope() != 0) {
                return deny("EDK_SCOPE_NOT_EXCLUSIVE");
            }
        }

        return request.phase() == Phase.SCHEDULE
                ? new Decision(true, "ALLOW_SCHEDULE")
                : new Decision(true, "ALLOW_FINALIZE");
    }

    private static Inventory inventory(
            boolean complete,
            int edks,
            int edksOutsideScope,
            int backupCopies,
            int replicas,
            int escrow,
            int alternativePaths,
            int plaintextCaches,
            boolean noLegalHold,
            boolean revalidated) {
        return new Inventory(
                complete,
                edks,
                edksOutsideScope,
                0,          // unresolved child keys
                backupCopies,
                replicas,
                escrow,
                alternativePaths,
                plaintextCaches,
                0,          // known external plaintext copies
                noLegalHold,
                true,       // retention satisfied
                true,       // all EDKs in approved erasure scope
                true,       // no new Wrap operations
                true,       // temporary grants revoked
                true,       // dry run passed
                revalidated,
                revalidated);
    }

    private static Approval approved() {
        return new Approval(
                true, true, true, true, true, true, true);
    }

    private static void show(String label, Request request) {
        Decision d = evaluate(request);
        System.out.println(label + ": "
                + d.allowed() + " / " + d.reason());
    }

    public static void main(String[] args) {
        KeyRef tenantKek = new KeyRef(
                "ExampleKMS",
                "prod-account",
                "region-a",
                "tenant-42-kek",
                4,
                "tenant-42",
                "DATA_KEY_WRAPPING");

        // Retirement: mọi EDK đã rewrap và inventory không còn dependency.
        Inventory retiredInventory = inventory(
                true, 0, 0, 0, 0, 0, 0, 0,
                true, false);
        Request retirement = new Request(
                tenantKek,
                Intent.RETIRE_AFTER_MIGRATION,
                Phase.SCHEDULE,
                KeyState.DISABLED,
                retiredInventory,
                approved(),
                false);
        show("Retirement schedule", retirement);

        // Crypto-erasure: EDK còn tồn tại nhưng tất cả nằm trong scope.
        Inventory erasureInventory = inventory(
                true, 1200, 0, 0, 0, 0, 0, 0,
                true, false);
        Request erasure = new Request(
                tenantKek,
                Intent.CRYPTO_ERASURE,
                Phase.SCHEDULE,
                KeyState.DISABLED,
                erasureInventory,
                approved(),
                false);
        show("Crypto-erasure schedule", erasure);

        // Một EDK nằm ngoài scope: không được destroy shared KEK.
        Inventory mixedScope = inventory(
                true, 1200, 1, 0, 0, 0, 0, 0,
                true, false);
        show("EDK outside scope", new Request(
                tenantKek, Intent.CRYPTO_ERASURE, Phase.SCHEDULE,
                KeyState.DISABLED, mixedScope, approved(), false));

        // Inventory không đầy đủ: UNKNOWN phải fail closed.
        Inventory incomplete = inventory(
                false, 0, 0, 0, 0, 0, 0, 0,
                true, false);
        show("Incomplete inventory", new Request(
                tenantKek, Intent.RETIRE_AFTER_MIGRATION,
                Phase.SCHEDULE, KeyState.DISABLED,
                incomplete, approved(), false));

        // Plaintext DEK cache vẫn còn: destroy chưa đủ để crypto-erase.
        Inventory cachedDek = inventory(
                true, 1200, 0, 0, 0, 0, 0, 2,
                true, false);
        show("Plaintext DEK cache remains", new Request(
                tenantKek, Intent.CRYPTO_ERASURE, Phase.SCHEDULE,
                KeyState.DISABLED, cachedDek, approved(), false));

        // Finalize chỉ sau waiting period và revalidation.
        Inventory finalInventory = inventory(
                true, 1200, 0, 0, 0, 0, 0, 0,
                true, true);
        show("Finalize after waiting period", new Request(
                tenantKek, Intent.CRYPTO_ERASURE, Phase.FINALIZE,
                KeyState.PENDING_DELETION,
                finalInventory, approved(), true));

        show("Finalize before waiting period", new Request(
                tenantKek, Intent.CRYPTO_ERASURE, Phase.FINALIZE,
                KeyState.PENDING_DELETION,
                finalInventory, approved(), false));
    }
}
~~~

Lưu thành **DestroyKekGateDemo.java** và chạy bằng JDK 17+:

~~~bash
javac DestroyKekGateDemo.java
java DestroyKekGateDemo
~~~

Kết quả logic dự kiến:

~~~text
Retirement schedule: true / ALLOW_SCHEDULE
Crypto-erasure schedule: true / ALLOW_SCHEDULE
EDK outside scope: false / EDK_SCOPE_NOT_EXCLUSIVE
Incomplete inventory: false / INVENTORY_INCOMPLETE
Plaintext DEK cache remains: false / PLAINTEXT_DEK_COPY_OR_CACHE_REMAINS
Finalize after waiting period: true / ALLOW_FINALIZE
Finalize before waiting period: false / WAITING_PERIOD_NOT_ELAPSED
~~~

### 11.1. Vì sao retirement và crypto-erasure có điều kiện khác nhau?

Với **retirement**, không được còn EDK nào cần giữ mà chỉ mở được bằng KEK cũ. Vì mục tiêu là giữ dữ liệu truy cập được, EDK phải được rewrap/re-encrypt hoặc đã hết retention.

Với **crypto-erasure**, EDK có thể vẫn còn trong storage vì chính chúng nằm trong scope cần mất khả năng mở. Nhưng phải chứng minh **mọi EDK đó đều thuộc scope**, không có EDK ngoài scope và không có alternative wrapping/recovery path.

### 11.2. Những gì code không thực hiện

1. Không gọi DeleteKey, HSM zeroize hoặc provider API.
2. Không kiểm kê thật database, backup, replicas, escrow hay process memory.
3. Không chứng minh một DEK plaintext đã bị xóa khỏi mọi host.
4. Không thực thi legal hold; các cờ approval chỉ mô phỏng.
5. Không có signed approvals, IdP/MFA, quorum cryptographic shares hoặc immutable audit.
6. Không biết semantics deletion/waiting period của bất kỳ provider cụ thể nào.
7. Không chứng minh attacker không giữ raw key hoặc plaintext đã copy.
8. Không thay thế dependency graph, dry-run và independent review.

**Policy gate là một lớp ngăn thao tác nhầm**, không phải bằng chứng rằng key đã bị hủy. Provider result và system-wide evidence phải được thu thập riêng.

## 12. Threat model: Điều gì có thể làm crypto-erasure thất bại?

### 12.1. Các đường khôi phục bị bỏ sót

| Nguy cơ | Hậu quả | Kiểm soát |
|---|---|---|
| **HSM backup blob còn tồn tại** | Có thể restore lại KEK | Inventory backup, xử lý blob/wrapping key theo policy |
| **Recovery shares còn đủ threshold** | Có thể tái tạo recovery root | Thu hồi/reshare và destruction evidence |
| **Replica ở region khác** | Key vẫn hoạt động ở DR | Đối soát tất cả regions/accounts/partitions |
| **Alternative KEK đã wrap cùng DEK** | EDK vẫn mở được qua key khác | Dependency graph EDK → mọi wrapping paths |
| **Plaintext DEK cache còn sống** | Có thể decrypt offline sau khi KEK bị hủy | Drain workloads, expire leases, verify caches |
| **Raw DEK export từng được tạo** | Bản sao nằm ngoài KMS | BYOK/export inventory, secret scanning và forensics |
| **External partner giữ DEK/EDK** | Tổ chức không thể tuyên bố xóa trên mọi copy | Data lineage, contract và partner confirmation |
| **Memory dump/crash report** | Secret có thể nằm trong artifact | Dump/swap controls, retention cleanup, incident review |
| **Backup key dùng để wrap chính backup** | Backup có thể restore qua đường chưa tính | Inventory hierarchy và independent recovery review |
| **Provider retention không được hiểu** | Delete request chưa đồng nghĩa material bị xóa | Xác minh final state và provider contract |

### 12.2. Các lỗi quy trình

- **Sai key ID/version:** destroy alias đã đổi sang key khác, hoặc destroy production thay vì test.
- **Inventory stale:** query thiếu page, replica chưa đồng bộ, archive chưa đăng ký.
- **Approval sai scope:** phê duyệt tenant A nhưng operator chọn key chung cho A/B.
- **Quorum giả:** nhiều approvals từ một identity hoặc cùng failure domain.
- **Legal hold bỏ sót:** data owner không biết hồ sơ đang được điều tra.
- **Premature finalization:** kết thúc pending deletion trước khi revalidate dependencies.
- **Audit không độc lập:** operator có thể sửa/xóa evidence.
- **Recovery path còn mở:** một nhóm khác có quyền restore key từ backup.

### 12.3. Insider threat và separation of duties

Một người có thể lạm dụng destroy để gây mất dữ liệu, hoặc trì hoãn destroy để giữ một đường giải mã ngoài policy. Với KEK có blast radius lớn, cần:

1. Tách **requester, owner, approver, operator và auditor**.
2. Ràng buộc approval với **keyRef/version, tenant, intent, action và request ID**.
3. Yêu cầu quorum/dual control theo classification.
4. Giữ audit ở hệ thống mà operator không thể tự xóa.
5. Gửi alert độc lập khi key chuyển DISABLED, PENDING_DELETION hoặc DESTROYED.
6. Có break-glass process được phê duyệt, có expiry và post-review.

**Không dùng một approval “đồng ý xóa KEK” chung chung** cho mọi key/version hoặc mọi loại hành động. Approval phải xác định rõ destroy hay disable, retirement hay crypto-erasure.

### 12.4. Availability và integrity

Destroy nhầm KEK có thể gây:

- Không đọc được dữ liệu khách hàng.
- Không restore được backup.
- Mất khả năng decrypt archive hoặc xử lý giao dịch đang chờ.
- Không khôi phục được child KEKs.
- Gãy DR và vi phạm RTO/RPO.
- Mất khả năng ký/verify nếu key hierarchy dùng chung sai purpose.

Để tránh:

- Không dùng wildcard/prefix để chọn key.
- Dùng dry-run và exact immutable key identity.
- Revalidate dependency inventory ngay trước final deletion.
- Kiểm tra parent/child relationships và scope của tenant.
- Test recovery với key mới trước khi hủy key cũ trong retirement.

## 13. Runbook Destroy KEK

### 13.1. Trước khi submit request

1. **Xác định intent:** retirement sau migration hay crypto-erasure.
2. **Xác định exact key:** provider/account/region/partition/key ID/version/tenant/purpose.
3. **Xác định scope:** dữ liệu, EDK, child keys, backups, replicas, archive, external copies.
4. **Lập dependency graph:** liệt kê mọi đường mở, backup và recovery paths.
5. **Đối chiếu retention/legal hold:** nhận approval từ đúng owner/legal/compliance.
6. **Kiểm tra plaintext DEK exposure:** cache, JVM, worker, swap, dump, export và downstream.
7. **Chọn migration:** rewrap nếu giữ DEK; re-encrypt nếu cần đổi DEK.
8. **Xác nhận backup/DR:** test restore theo hierarchy mới nếu retirement.
9. **Chọn quorum/dual control:** approvers độc lập với requester/operator.
10. **Đọc provider deletion semantics:** disable, pending window, cancellation, final deletion và backup retention.

### 13.2. Trong quá trình hủy

~~~text
T0: Freeze new Wrap operations on target KEK.
T1: Revalidate keyRef/version and dependency inventory.
T2: Verify no legal hold / retention conflict.
T3: Verify no plaintext DEK cache or active workload dependency.
T4: Obtain owner + security + quorum approvals.
T5: Run exact-key dry-run and independent review.
T6: Disable or schedule deletion under provider semantics.
T7: Monitor waiting/cancellation window.
T8: Revalidate inventory and approvals.
T9: Finalize deletion with exact key identity.
T10: Verify provider final state and system dependencies.
T11: Close grants, sessions, shares and ceremony.
~~~

### 13.3. Sau khi destroy

- Kiểm tra provider báo **final deletion/destroyed** theo contract.
- Xác minh key không còn thực hiện được crypto operations trong phạm vi provider.
- Đối soát replicas, backup, escrow, recovery shares và imported material.
- Xác minh workloads không còn cache/plaintext DEK được biết.
- Kiểm tra EDK trong scope crypto-erasure không còn alternative wrapping path.
- Nếu retirement, restore dữ liệu cần giữ bằng KEK hierarchy mới.
- Cập nhật key registry/destruction register và xóa aliases/grants theo policy.
- Giữ audit evidence, approvals, timestamps, provider request IDs và scope.
- Thông báo các owners/consumers bị ảnh hưởng theo quy trình nội bộ.

### 13.4. Nếu phát hiện dependency sau khi đã schedule

Nếu còn trong cancellation window:

1. Dừng finalization.
2. Cancel deletion nếu provider hỗ trợ và policy cho phép.
3. Xác minh key đã enable lại hay chỉ hủy lịch; không giả định tự động.
4. Đánh giá dữ liệu/backup nào bị ảnh hưởng trong thời gian disable.
5. Reconcile key state và IAM grants.
6. Mở lại dependency inventory, sửa plan và approvals.

Nếu đã final destroy:

- Không giả định provider có thể khôi phục material.
- Kiểm tra backup/recovery paths có được phép và còn nguyên không.
- Đánh giá data loss/retention impact, thông báo incident commander và data owner.
- Không thử lấy key từ memory dump hoặc artifact ngoài quy trình forensic được phê duyệt.
- Ghi rõ khả năng phục hồi thực tế và giới hạn.

### 13.5. Nếu nghi KEK đã bị compromise

**Destroy KEK** có thể là một phần containment, nhưng không thay thế:

- Disable/revoke IAM grants và credentials bị lộ.
- Điều tra KMS/HSM Unwrap operations và raw DEK exposure.
- Xác định ciphertext/EDK/backup đã bị attacker copy.
- Rotate/re-encrypt DEKs nếu material có thể đã lộ.
- Kiểm tra child keys và KEKs được wrap bởi key bị compromise.
- Thu hồi recovery shares/backup wrapping key nếu cùng phạm vi bị ảnh hưởng.

**Nếu attacker đã có plaintext DEK, destroy KEK không thu hồi khả năng giải mã của attacker.**

## 14. Case study: Destroy tenant KEK sau khi khách hàng chấm dứt dịch vụ

### 14.1. Bối cảnh

Một SaaS lưu:

~~~text
Tenant: tenant-42
Key: tenant-42-kek-v4
Purpose: DATA_KEY_WRAPPING
Provider: KMS region-a

Data:
  2.4 triệu EDK trong primary database
  3 bản backup database còn retention
  1 archive object store
  1 DR replica

Workloads:
  Customer Reader
  Billing Archive Reader
  Background migration worker
~~~

Khách hàng yêu cầu xóa dữ liệu cá nhân và chấm dứt dịch vụ. Tuy nhiên, một số hóa đơn phải giữ theo retention và một nhóm hồ sơ đang có legal hold. KEK-v4 còn wrap cả EDK của hai nhóm dữ liệu này.

### 14.2. Phân loại scope

| Data class | Yêu cầu | Quyết định |
|---|---|---|
| **Temporary customer profile** | Đủ điều kiện xóa theo retention | Có thể crypto-erase sau khi inventory đầy đủ |
| **Invoices under retention** | Phải giữ khả năng truy cập | Rewrap EDK sang KEK archive mới |
| **Legal-hold records** | Không được làm mất khả năng đọc | Giữ đường key hợp lệ theo legal approval |
| **Operational logs** | Có retention riêng, có thể chứa metadata | Rà soát và xử lý theo log policy |

Không thể destroy KEK-v4 ngay vì nó bảo vệ EDK của invoice và legal-hold records ngoài scope. Team phải **tách dependency** trước.

### 14.3. Kế hoạch

**Bước 1 — Freeze:** Ngừng Wrap mới dưới KEK-v4 và chuyển writes sang KEK-v5 cho các dữ liệu còn hoạt động.

**Bước 2 — Preserve:** Rewrap EDK của invoices/legal-hold records sang KEK archive được phê duyệt; xác minh backup và restore.

**Bước 3 — Erasure scope:** Xác định toàn bộ EDK của temporary profiles; xác minh không có alternative wrapping path hoặc external plaintext DEK copies.

**Bước 4 — Stop consumers:** Drain reader/migration workloads, thu hồi grants và xác nhận cache leases hết hạn.

**Bước 5 — Review:** Data owner, legal/compliance và security phê duyệt phạm vi crypto-erasure. Auditor xác minh inventory.

**Bước 6 — Destroy:** Schedule deletion theo provider semantics, chờ window và revalidate dependencies; final destroy theo quorum.

**Bước 7 — Verify:** Kiểm tra KEK-v4 không còn dùng được, EDK trong erasure scope không thể Unwrap qua key hierarchy được quản lý, invoices/legal-hold records vẫn đọc được bằng archive KEK.

### 14.4. Điều gì sẽ là kết quả sai?

- Destroy KEK-v4 làm invoice mất khả năng đọc.
- EDK của temporary profiles đã rewrap sang KEK-v5 mà vẫn tuyên bố crypto-erasure thành công.
- Một backup cũ chứa KEK-v4 hoặc HSM backup blob có thể restore lại material.
- Reader vẫn cache plaintext DEK và tiếp tục decrypt sau khi KMS key bị destroy.
- Legal hold bị bỏ qua vì data owner chỉ duyệt yêu cầu xóa.

### 14.5. Evidence để đóng yêu cầu

- KeyRef/version và provider final deletion status.
- Dependency report có timestamp và coverage.
- EDK scope counts và mapping tới data classes.
- Rewrap/restore test cho invoices/legal-hold records.
- Workload drain/cache/temporary-grant evidence.
- Backup/replica/escrow/recovery path review.
- Legal/compliance approval và quorum ceremony record.
- Kết quả kiểm tra crypto operations sau destroy.

**Không tuyên bố xóa mọi bản sao ngoài tổ chức** nếu hợp đồng/partner confirmation hoặc technical evidence không hỗ trợ kết luận đó.

## 15. Audit, monitoring và destruction evidence

### 15.1. Destruction register

Mỗi KEK destroy request nên có một hồ sơ theo dõi riêng:

| Field | Nội dung |
|---|---|
| **Request/incident ID** | ID duy nhất cho destruction ceremony |
| **Target keyRef/version** | Provider, account, region, partition, immutable key ID/version |
| **Tenant/purpose/owner** | Phạm vi nghiệp vụ và người chịu trách nhiệm |
| **Intent** | RETIRE_AFTER_MIGRATION hoặc CRYPTO_ERASURE |
| **Data scope** | Data classes, tenant, record/object range, retention |
| **Dependency snapshot** | EDK, child keys, backup, replica, escrow, cache và alternative paths |
| **Inventory source/time** | Nguồn dữ liệu, snapshot time, coverage và pagination |
| **Approvals/quorum** | Actor IDs, role, MFA result, policy revision, expiry |
| **Dry-run result** | Target identity, dependency checks, blockers |
| **Provider lifecycle** | Disable/schedule/finalize request IDs và timestamps |
| **Waiting period** | Start/end, cancellation decision và revalidation |
| **Final state** | Provider final status và evidence reference |
| **Independent verification** | Auditor, checks, result và timestamp |
| **Exceptions/limitations** | External copies không quan sát được, provider-managed retention |

### 15.2. Không ghi secret vào audit

Nên ghi:

- Key ID/version, provider, tenant reference, action và result.
- Actor/approver/operator IDs, role, request ID và policy revision.
- Dependency counts, inventory source, dry-run result.
- Provider API request IDs, lifecycle state, effective time.
- HSM device/partition identifier và ceremony outcome.
- Backup/replica/escrow disposition reference.

Không ghi:

- Raw KEK/DEK, plaintext recovery root hoặc share bytes.
- PIN, activation secret, OTP, recovery password.
- Plaintext customer data hoặc toàn bộ EDK nếu không cần.
- KMS response body có chứa material/secret.
- Private key, HSM security officer credentials hoặc admin tokens.

**Audit log cũng là tài sản cần bảo vệ**. Người thực hiện destroy không nên có quyền xóa evidence; cần tamper-evident storage, retention và independent access review.

### 15.3. Metric cần theo dõi

- **KEKs không có owner/purpose/retention classification**.
- **Key dependencies chưa biết** hoặc inventory chưa complete.
- **EDK references còn lại** theo KEK version và data class.
- **Old KEK còn Wrap mới** sau khi retirement bắt đầu.
- **Backup/replica/escrow copies** chưa xử lý.
- **Plaintext DEK cache leases** còn sống sau khi disable.
- **Pending deletion** gần tới finalization nhưng chưa revalidate.
- **Destroy requests bị cancel** do phát hiện dependency.
- **Temporary grants** chưa thu hồi sau ceremony.
- **Recovery/restore tests thất bại** với key hierarchy mới.
- **Keys destroyed nhưng external dependencies chưa có owner**.

Một metric bằng zero chỉ có ý nghĩa khi **nguồn đo đầy đủ và đúng scope**. Nếu inventory không quan sát được một external archive, không được hiển thị dependency count = 0 như bằng chứng tuyệt đối.

### 15.4. Bằng chứng hủy cần có nhiều lớp

| Lớp evidence | Điều chứng minh |
|---|---|
| **Approval evidence** | Hành động và phạm vi được phê duyệt |
| **Inventory evidence** | Dependencies đã được xác định và xử lý |
| **Provider evidence** | Key object/material đã đạt final deletion state theo provider |
| **Operational evidence** | Workloads, grants, cache, replicas và recovery paths đã được xử lý |
| **Data evidence** | Ciphertext/EDK trong scope đã được xử lý theo mục tiêu |
| **Independent review** | Một người/nhóm độc lập đã đối soát kết quả |

Không có một loại log đơn lẻ nào chứng minh mọi lớp. **Provider DeleteKey success** là evidence quan trọng, nhưng không tự thay thế inventory, data lineage và cache review.

### 15.5. Phát biểu kết quả chính xác

Ví dụ phát biểu phù hợp:

> KEK tenant-42 version 4 đã đạt trạng thái final deletion theo provider tại thời điểm ghi nhận. Inventory của các hệ thống được quản lý cho thấy không còn backup/replica/escrow hoặc alternative wrapping path trong phạm vi đã kiểm tra. Plaintext DEK caches đã được drain theo quy trình. EDK thuộc scope crypto-erasure không còn đường Unwrap hợp lệ qua key hierarchy được quản lý. Các bản sao ngoài phạm vi quan sát được nêu riêng trong hồ sơ.

Tránh phát biểu vượt quá evidence như **“mọi byte của dữ liệu trên toàn thế giới đã bị xóa vĩnh viễn”**.

## 16. Checklist trước khi Destroy KEK

1. **Intent:** Đã xác định rõ retirement sau migration hay intentional crypto-erasure?
2. **Identity:** Key provider/account/region/partition/key ID/version đã xác định bất biến?
3. **Purpose:** Đúng KEK, đúng tenant/environment, không chọn nhầm alias hoặc key dùng chung?
4. **Owner:** Có key owner và service/data owners xác nhận?
5. **Scope:** Đã xác định dữ liệu nào cần giữ, dữ liệu nào được phép crypto-erase?
6. **Retention:** Legal hold, investigation, contract và retention obligations đã được kiểm tra?
7. **Hierarchy:** Đã lập parent/child key graph và xác định blast radius?
8. **EDK inventory:** Đã tìm EDK trong primary DB, archive, queues, object stores và backups?
9. **DEK inventory:** Đã xác định DEKs/child KEKs được bảo vệ bởi target KEK?
10. **Alternative wraps:** Có EDK nào được wrap thêm bởi KEK khác hoặc recovery key khác?
11. **Backup:** HSM backup blobs, database snapshots, tapes và offline media đã được rà soát?
12. **Replica:** Tất cả regions/accounts/partitions/DR clusters đã được đối soát?
13. **Escrow/quorum:** Recovery shares, split knowledge, escrow và break-glass packages đã được xử lý?
14. **Imported material:** BYOK source files, import packages và staging copies đã được kiểm kê?
15. **Exported material:** Raw key exports hoặc secret copies có thể còn tồn tại?
16. **Plaintext cache:** Workloads đã Unwrap DEK đã được drain, cache lease hết hạn và dump/swap review?
17. **External copies:** Partner, downstream systems và data exports đã có owner/confirmation?
18. **Migration:** Nếu retirement, EDK đã rewrap hoặc data đã re-encrypt đúng mục tiêu?
19. **Restore:** Backup mới đã restore end-to-end bằng hierarchy mới?
20. **Crypto-erasure scope:** Nếu crypto-erase, mọi EDK còn lại đều thuộc scope được duyệt và không có EDK ngoài scope?
21. **No-new-use:** KEK đã ngừng Wrap mới và không còn grants/workloads dùng nó?
22. **Provider semantics:** Disable, pending deletion, cancel window, final deletion và backup retention đã được xác minh?
23. **Dry-run:** Exact target, dependencies, affected tenants và expected impact đã được review?
24. **Approvals:** Owner, security, legal/compliance và quorum/dual control đã phê duyệt đúng action?
25. **Separation of duties:** Requester, approver, executor và auditor được tách theo policy?
26. **Waiting period:** Hold window đã được tính và có quy trình cancellation?
27. **Revalidation:** Inventory được kiểm tra lại ngay trước finalization, không có dependency mới?
28. **Provider execution:** Request ID, final status và timestamp được lưu?
29. **Operational cleanup:** Temporary grants, sessions, shares, aliases và credentials đã được xử lý?
30. **Independent verification:** Auditor xác minh provider state và dependency evidence?
31. **Data verification:** Ciphertext/EDK ngoài scope vẫn truy cập được; dữ liệu trong crypto-erasure scope không còn đường mở được quản lý?
32. **Audit hygiene:** Không ghi raw key, plaintext DEK, share, PIN hoặc token vào log/ticket?
33. **Incident check:** Nếu key compromise, đã xử lý attacker copies, credentials và DEK exposure riêng?
34. **Evidence scope:** Hồ sơ nêu rõ nguồn inventory, thời điểm, coverage và giới hạn quan sát?
35. **Final acceptance:** Có thể chứng minh đúng key đã hủy, đúng phạm vi và không làm mất dữ liệu cần giữ?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** KEK dùng để làm gì trong envelope encryption?

**Trả lời:** KEK bảo vệ DEK bằng Wrap/Unwrap hoặc cơ chế tương đương. DEK trực tiếp mã hóa dữ liệu; EDK là DEK đã được wrap và thường lưu cùng ciphertext.

**Câu 2.** Hủy KEK có tự động xóa ciphertext không?

**Trả lời:** **Không.** Ciphertext có thể vẫn nằm trong database/backup; hủy KEK chỉ có thể loại bỏ một đường giải mã nếu không còn material/copy/alternative path.

**Câu 3.** Disable KEK có tương đương destroy không?

**Trả lời:** **Không.** Disable thường chặn operations nhưng material hoặc backup có thể vẫn tồn tại và có thể enable/restore lại.

**Câu 4.** Retire KEK khác crypto-erasure thế nào?

**Trả lời:** Retirement nhằm ngừng dùng KEK cũ nhưng giữ dữ liệu đọc được bằng cách rewrap/migrate. Crypto-erasure chủ đích làm dữ liệu trong scope không còn khả năng mở qua key paths được quản lý.

**Câu 5.** Khi rotation KEK nhưng muốn giữ dữ liệu, nên làm gì với EDK?

**Trả lời:** Rewrap EDK dưới KEK mới hoặc dùng cơ chế migration tương đương, xác minh restore và backup trước khi destroy KEK cũ.

**Câu 6.** Rewrap EDK có thay DEK không?

**Trả lời:** **Không.** Rewrap đổi lớp bảo vệ của cùng DEK. Muốn đổi DEK cần re-encrypt content hoặc quy trình thay key tương ứng.

**Câu 7.** Nếu plaintext DEK vẫn nằm trong JVM cache, destroy KEK có đủ crypto-erase không?

**Trả lời:** **Không.** Process có thể tiếp tục dùng DEK offline. Cần drain workloads, expire leases và xử lý mọi bản sao plaintext.

**Câu 8.** Nếu HSM backup blob còn có thể restore KEK, có thể tuyên bố KEK đã bị crypto-erased không?

**Trả lời:** **Không.** Backup/recovery path còn tồn tại có thể tái tạo key. Phải xử lý theo provider semantics và inventory.

**Câu 9.** Vì sao phải inventory child KEKs trước khi hủy parent KEK?

**Trả lời:** Parent KEK có thể wrap child KEKs. Destroy parent có thể làm mất đường phục hồi toàn bộ nhánh hierarchy, vượt phạm vi dữ liệu dự định.

**Câu 10.** EDK count bằng zero có chứng minh không còn đường giải mã không?

**Trả lời:** **Không.** Plaintext DEK, alternative wrappers, exports, backup, replicas hoặc external copies có thể còn.

**Câu 11.** Crypto-erasure có thể áp dụng khi có legal hold không?

**Trả lời:** Không nếu việc đó vi phạm yêu cầu hold/retention. Phải được legal/compliance review trước.

**Câu 12.** Provider DeleteKey trả success có chứng minh mọi backup và external copies đã bị xóa không?

**Trả lời:** **Không.** Nó chứng minh kết quả theo API/provider contract. Backup, replicas, imported material, caches và external copies cần evidence riêng.

**Câu 13.** Vì sao phải phân biệt pending deletion và destroyed?

**Trả lời:** Pending deletion có thể còn waiting period/cancel window và semantics khác nhau theo provider. Chỉ final deletion state mới cho biết provider đã hoàn tất bước hủy theo contract.

**Câu 14.** Có nên dùng alias current để xác định KEK cần hủy?

**Trả lời:** **Không.** Alias có thể đã đổi target. Dùng immutable key ID/version và xác minh provider/account/region/partition.

**Câu 15.** Một KEK có alternative wrapping path qua KEK-v2, có thể crypto-erase bằng cách hủy KEK-v1 không?

**Trả lời:** **Không.** DEK vẫn có thể mở qua KEK-v2. Phải xử lý alternative path trong scope hoặc không tuyên bố crypto-erasure.

**Câu 16.** Nếu attacker đã copy plaintext DEK trước khi KEK bị destroy, họ có còn giải mã ciphertext đã copy không?

**Trả lời:** **Có thể.** Destroy KEK không thu hồi bản plaintext DEK và ciphertext mà attacker đã lấy.

**Câu 17.** Vì sao cần revalidate dependency inventory trong waiting period?

**Trả lời:** Vì có thể xuất hiện dependency mới, migration chưa hoàn tất hoặc backup/replica bị bỏ sót. Trạng thái trước khi schedule không tự đảm bảo vẫn đúng lúc finalize.

**Câu 18.** Có nên cho operator tự request, approve, execute và audit destroy?

**Trả lời:** **Không.** Cần separation of duties, quorum/dual control và audit độc lập.

**Câu 19.** Destroy một KEK có cần xem imported/BYOK source files không?

**Trả lời:** **Có.** Xóa key object trong KMS không nhất thiết xóa file nguồn, import package hoặc bản sao ngoài provider.

**Câu 20.** Nếu target KEK wrap cả EDK của tenant A và B, có thể destroy để crypto-erase riêng tenant A không?

**Trả lời:** **Không an toàn** nếu chưa tách dependency. Cần KEK riêng hoặc rewrap dữ liệu tenant B sang key khác trước khi hủy shared KEK.

**Câu 21.** Khi nào có thể hủy KEK sau retirement?

**Trả lời:** Khi mọi dữ liệu/backup cần giữ đã có đường phục hồi mới, không còn dependency hợp lệ, restore drill thành công, grants/cache/recovery copies được xử lý và approvals hoàn tất.

**Câu 22.** HSM zeroize có giống destroy một key object không?

**Trả lời:** **Không nhất thiết.** Zeroize có thể tác động tới cả partition/device; destroy object có thể chỉ xóa một key. Cần xác minh semantics và blast radius.

**Câu 23.** Crypto-erasure có thay thế storage deletion không?

**Trả lời:** **Không hoàn toàn.** Ciphertext vẫn có thể tồn tại; nếu yêu cầu là xóa bytes khỏi storage, cần lifecycle deletion riêng cho primary, backup, archive và replicas.

**Câu 24.** Vì sao recovery shares phải được rà soát khi destroy KEK?

**Trả lời:** Shares có thể tái tạo recovery root hoặc key backup. Nếu vẫn đủ threshold, material có thể được khôi phục sau khi key object bị xóa.

**Câu 25.** Nếu inventory không đầy đủ nhưng mọi count hiện tại đều bằng zero, có được finalize không?

**Trả lời:** **Không.** UNKNOWN không phải zero; thiếu evidence phải fail closed.

**Câu 26.** Sau khi destroy KEK, có nên giữ lại audit record không?

**Trả lời:** **Có.** Giữ metadata, approvals, provider request IDs, timestamps và verification evidence theo retention; không giữ raw key/share.

**Câu 27.** Vì sao cần test backup restore bằng hierarchy mới trước khi destroy old KEK?

**Trả lời:** Để chứng minh dữ liệu cần giữ có thể mở bằng key mới và backup không còn phụ thuộc old KEK.

**Câu 28.** Crypto-erasure có thể chứng minh attacker không còn bản sao đã lấy trước đó không?

**Trả lời:** **Không.** Nó chỉ có thể chứng minh các key paths được quản lý đã bị loại bỏ trong phạm vi evidence; bản sao attacker giữ nằm ngoài khả năng thu hồi.

**Câu 29.** Một KEK đã bị compromise có nên restore từ backup rồi tiếp tục dùng không?

**Trả lời:** **Không nên mặc định.** Restore cùng material không loại bỏ compromise. Cần thay key, đánh giá DEK exposure, rewrap/re-encrypt và xử lý backup/recovery paths.

**Câu 30.** Bằng chứng nào cần có để đóng một destruction request?

**Trả lời:** Exact key identity, approved intent/scope, dependency inventory, legal/retention review, provider final deletion evidence, backup/replica/cache handling và independent verification.

## 18. Tổng kết

**Destroy KEK** là bước quan trọng trong vòng đời khóa nhưng cũng có thể là thao tác gây mất dữ liệu không thể đảo ngược. Trước khi hủy phải biết KEK đang bảo vệ **DEK, EDK, child keys, backup và recovery paths nào**, cũng như mục tiêu là **retire sau migration** hay **crypto-erase có chủ đích**.

Những nguyên tắc cần giữ:

- **Không nhầm trạng thái:** disable/retire/revoke/pending deletion không đồng nghĩa destroyed.
- **Kiểm kê trước khi hủy:** dependency graph phải bao phủ EDK, child keys, backup, replicas, escrow, imported/exported material và plaintext DEK caches.
- **Phân biệt hai intent:** retirement phải giữ dữ liệu truy cập được; crypto-erasure cố ý làm mất đường mở cho đúng scope.
- **Rewrap khác re-encrypt:** rewrap đổi KEK nhưng giữ DEK; re-encrypt thay DEK và content ciphertext.
- **Hiểu provider semantics:** KMS deletion window, HSM object destruction, zeroization, backup retention và external key store có hành vi riêng.
- **Thực hiện có kiểm soát:** dry-run, exact key identity, legal review, quorum, dual control, waiting period và independent audit.
- **Không tuyên bố quá evidence:** destroy KEK không xóa ciphertext, không thu hồi DEK attacker đã copy và không tự xử lý mọi external backup.
- **Kiểm chứng sau hủy:** provider final state, replicas, recovery shares, cache, IAM và data scope phải được đối soát.

**Điểm cốt lõi:** Hủy KEK an toàn không phải là gọi một API DeleteKey. Đó là một quyết định có phạm vi, bằng chứng và kiểm soát: **đúng key, đúng dữ liệu, đúng mục đích, đúng approvals, đúng provider semantics và không còn đường phục hồi ngoài ý muốn**.
