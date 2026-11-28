# Không backup key không còn cần thiết

## 1. Nguyên tắc: chỉ sao lưu khóa còn có nhu cầu phục hồi hợp lệ

**Backup key** là việc tạo và duy trì một bản sao có kiểm soát của vật liệu khóa hoặc cơ chế đủ để khôi phục khả năng sử dụng khóa khi xảy ra mất mát, hỏng thiết bị, lỗi vùng triển khai hoặc thảm họa. Backup có thể là bản sao vật liệu được mã hóa, bản sao trong HSM dự phòng, key shares theo threshold scheme hoặc một cơ chế recovery do KMS provider quản lý.

Nguyên tắc **“Không backup key không còn cần thiết”** có nghĩa là tổ chức phải chứng minh một key material còn phục vụ **mục đích nghiệp vụ, giải mã dữ liệu lịch sử, xác minh chữ ký, tuân thủ lưu trữ hoặc phục hồi thảm họa** trước khi tiếp tục duy trì bản backup của nó. Khi mọi dependency đã kết thúc và retention cho phép hủy, không nên tiếp tục lưu bản sao khóa chỉ vì “có thể một ngày nào đó cần”.

Ngược lại, một khóa đã dừng mã hóa dữ liệu mới **chưa chắc đã không còn cần thiết**. Một DEK có thể vẫn cần để giải mã archive; một public key/certificate có thể vẫn cần để xác minh chữ ký cũ; một KEK có thể vẫn bọc những DEK trong snapshot nhiều năm. Xóa backup của các khóa này trước khi xử lý dependency có thể làm dữ liệu không thể phục hồi.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học này thuộc chương **Backup và recovery**, kết nối:

- Vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, rotation, revocation đến destruction.
- Khóa đối xứng và bất đối xứng, chữ ký số, HMAC, KMS/HSM.
- Envelope encryption, DEK/KEK, key wrapping và key inventory.
- Backup/restore, disaster recovery, cryptoperiod, retention và crypto-shredding.
- Kiểm soát truy cập, separation of duties, audit và ứng phó sự cố.

**Ghi nhớ:** Chỉ backup vật liệu cần thiết để phục hồi một mục tiêu được phê duyệt. **Không duy trì backup của key đã hết mọi dependency, đã hết retention hoặc đã bị compromise như thể nó vẫn là khóa phục hồi hợp lệ.** Backup cần thiết phải được bảo vệ độc lập, kiểm tra restore và có thời hạn kết thúc.

## 2. Vì sao không nên backup mọi key?

Mỗi bản sao khóa là một nơi attacker có thể tìm cách lấy secret. Khi một key được nhân bản sang nhiều vault, backup media, snapshot, máy dự phòng hoặc escrow, phạm vi cần bảo vệ và kiểm toán tăng lên.

| Rủi ro | Điều có thể xảy ra |
|---|---|
| **Attack surface tăng** | Nhiều bản sao, nhiều credentials và nhiều nơi lưu trữ trở thành mục tiêu |
| **Retention không giới hạn** | Key cũ tiếp tục giải mã dữ liệu lâu sau khi purpose kết thúc |
| **Compromise lan rộng** | Attacker lấy backup copy có thể dùng offline, không cần KMS chính |
| **Sai lệch phiên bản** | Restore nhầm key material, alias hoặc policy đã lỗi thời |
| **Khó thu hồi** | Không biết bản sao nào còn tồn tại để xóa hoặc thay |
| **Mất kiểm soát custody** | Backup nằm ngoài quorum, SoD hoặc quyền hạn ban đầu |
| **Khó chứng minh destruction** | Key vẫn tồn tại trong snapshot, media, escrow hoặc replica |
| **Chi phí và độ phức tạp** | Cần quản lý thêm encryption, inventory, access, rotation và restore |

### 2.1. Backup không tự động làm hệ thống an toàn hơn

Backup tăng khả năng phục hồi khi có lỗi, nhưng cũng tăng số bản sao secret. Một backup plaintext đặt ở storage dễ truy cập có thể biến một KMS non-exportable thành hệ thống có **bản sao key exportable ngoài KMS**.

### 2.2. “Để phòng khi cần” không phải mục đích đủ rõ

Mỗi backup phải có **owner, purpose, dependency, recovery objective, retention, access policy và destruction condition**. Nếu không thể chỉ ra dữ liệu hoặc quy trình nào cần key để phục hồi, việc giữ thêm bản sao cần được xem xét lại.

## 3. Phân biệt backup key, backup ciphertext và backup cấu hình

Các đối tượng sau liên quan nhưng không thay thế cho nhau:

| Đối tượng | Chứa gì? | Có phải bản sao key material không? |
|---|---|---|
| **Ciphertext backup** | Dữ liệu đã mã hóa | Không |
| **Encrypted DEK** | DEK được bọc dưới KEK | Không phải plaintext DEK; vẫn phụ thuộc KEK |
| **Plaintext DEK backup** | Bytes DEK rõ | Có; rủi ro cao |
| **KEK backup/export** | Vật liệu dùng bọc DEK | Có; thường cần HSM/controlled escrow |
| **KMS metadata/config backup** | Key ID, policy, grants, labels, aliases | Không chứa raw key theo mặc định |
| **HSM backup/replica** | Vật liệu được bảo vệ trong miền HSM | Có cơ chế phục hồi key, semantics phụ thuộc thiết bị/provider |
| **Recovery shares** | Các phần secret theo threshold scheme | Là thành phần có thể tái tạo secret |
| **Public key/certificate archive** | Public key và thông tin trust | Không phải private key secret |
| **Key inventory** | Metadata, owner, usage, dependencies | Không được chứa raw key bytes |

### 3.1. Backup ciphertext mà không có đường phục hồi key là backup chưa hoàn chỉnh

Một snapshot database chứa ciphertext và encrypted DEK nhưng không có KEK/recovery path hợp lệ có thể không giải mã được. Ngược lại, backup key không có ciphertext/metadata cần thiết cũng không phục hồi được ứng dụng.

### 3.2. Không đưa plaintext key vào backup ứng dụng

Không serialize raw DEK/KEK/private key vào database dump, application config, VM image, heap dump hoặc log chỉ để “đảm bảo restore”. Hãy dùng **key wrapping, HSM backup, KMS replication hoặc recovery ceremony** đã được thiết kế.

## 4. “Không còn cần thiết” phải được chứng minh như thế nào?

Một key chỉ nên được xem là không còn cần backup sau khi đánh giá toàn bộ dependency và retention. Những câu hỏi sau phải có câu trả lời:

1. Có producer nào còn Encrypt, Sign, MAC, Wrap hoặc dẫn xuất key dưới material này không?
2. Có consumer nào còn cần Decrypt, Verify, Unwrap hoặc xác thực dữ liệu lịch sử không?
3. Có ciphertext, encrypted DEK, archive, snapshot, backup, replica hoặc export nào còn phụ thuộc không?
4. Có yêu cầu pháp lý, hợp đồng, kiểm toán, tranh chấp hoặc legal hold không?
5. Có bản restore/rollback nào còn cần key trong cửa sổ recovery không?
6. Có chữ ký số, certificate chain hoặc timestamp cần xác minh lâu dài không?
7. Có recovery share, HSM replica hoặc provider-managed backup nào còn giữ material?
8. Có derived key hoặc child key nào phụ thuộc secret cha không?
9. Có ứng dụng offline, batch job, vùng DR hoặc đối tác chưa cutover không?
10. Owner và approver đã xác nhận mục đích kết thúc và evidence chưa?

### 4.1. Dependency clearance là điều kiện trước khi xóa backup

Không chỉ tìm key ID trong database hiện tại. Cần kiểm tra **mọi phiên bản dữ liệu, object storage, archive, snapshot, replicas, offline media, DR site và bản export đã gửi ra ngoài**.

### 4.2. Không thấy dependency không đồng nghĩa không có dependency

Nếu inventory thiếu hoặc audit không đầy đủ, trạng thái đúng là **unknown/evidence gap**, không phải “đã hết phụ thuộc”. Cần bổ sung điều tra hoặc risk acceptance trước khi loại bỏ khả năng phục hồi.

## 5. Vòng đời: active, decrypt-only, retired, revoked và destroyed

Một khóa có thể ngừng một số operation nhưng vẫn cần được giữ để phục vụ operation khác.

| Trạng thái | Encrypt/Sign mới | Decrypt/Verify lịch sử | Backup/recovery |
|---|---|---|---|
| **Active** | Được phép theo policy | Được phép | Theo recovery requirement |
| **Decrypt-only / Verify-only** | Không | Có thể được phép | Có thể vẫn bắt buộc |
| **Retired** | Không theo purpose cũ | Có thể cần trong retention | Giữ nếu còn dependency |
| **Revoked** | Không được phép theo policy | Tùy incident/type; có thể chỉ migration có kiểm soát | Không khôi phục như key hoạt động nếu bị compromise |
| **Pending destruction** | Không | Chỉ khi policy/provider cho phép và có kiểm soát | Chuẩn bị kết thúc dependency |
| **Destroyed** | Không | Không thể dùng material đã hủy | Không tạo backup operational mới |

### 5.1. Retire không đồng nghĩa không cần backup

Ví dụ một DEK đã retire vì ứng dụng chuyển sang DEK mới, nhưng encrypted archive vẫn còn trong thời hạn lưu trữ. DEK cũ có thể vẫn cần cho **Decrypt lịch sử**, nên recovery path của nó vẫn phải tồn tại.

### 5.2. Revoked do compromise khác retired theo lịch

Một key bị compromise không nên được khôi phục từ backup để tiếp tục dùng như cũ. Có thể cần giữ **evidence forensic** theo quy trình riêng, nhưng bản sao đó phải được cô lập, đánh dấu compromised và không được đưa lại vào hoạt động.

### 5.3. Destroyed là trạng thái cần evidence

Chỉ xóa alias, key reference hoặc metadata không chứng minh vật liệu đã bị hủy. Cần trạng thái provider/HSM, xác nhận xóa replica/recovery copies theo semantics thực tế và hồ sơ destruction.

## 6. Originator-use và recipient-use: khóa dừng mã hóa nhưng còn cần giải mã

Quản lý backup phải phân biệt:

- **Originator-use period:** thời gian key được phép tạo ciphertext, MAC hoặc chữ ký mới.
- **Recipient-use period:** thời gian key còn cần để Decrypt/Verify dữ liệu đã tạo trước đó.
- **Recovery/retention period:** thời gian tổ chức phải duy trì khả năng khôi phục dữ liệu và key dependencies.
- **Destruction eligibility:** thời điểm mọi dependency và nghĩa vụ lưu trữ đã kết thúc.

Ví dụ, DEK-A đã ngừng Encrypt từ tháng 6 khi chuyển sang DEK-B. Tuy nhiên, bản backup hóa đơn từ tháng 1 đến tháng 5 vẫn dùng DEK-A. Nếu dữ liệu phải lưu bảy năm, key recovery path phù hợp cũng có thể cần tồn tại trong thời gian đó, trừ khi dữ liệu được migrate/re-encrypt và xác minh đầy đủ.

### 6.1. Đừng kéo dài backup chỉ vì cryptoperiod đã kết thúc

Nếu dữ liệu đã hết retention, được xóa hợp lệ, không còn backup hoặc legal hold và mọi restore window đã đóng, việc tiếp tục giữ key backup có thể không có mục đích. Khi đó cần quy trình destruction có kiểm chứng.

### 6.2. Đừng xóa key chỉ vì originator-use period kết thúc

Ngừng Encrypt mới không đồng nghĩa xóa khả năng Decrypt. Việc loại bỏ backup quá sớm có thể làm mất dữ liệu lịch sử dù hệ thống hiện tại vẫn hoạt động bình thường.

## 7. Phân loại nhu cầu backup theo key type

| Loại key | Nhu cầu backup/recovery thường gặp | Khi nào không nên giữ backup |
|---|---|---|
| **DEK theo object** | Giữ encrypted DEK cùng ciphertext và recovery path của KEK | Object đã hết retention, không còn archive/legal hold |
| **DEK theo tenant/database** | Cần khôi phục dữ liệu lịch sử và backup snapshots | Đã migrate toàn bộ data/backup, verify và clearance |
| **KEK trong KMS/HSM** | Provider replication, HSM backup hoặc recovery ceremony theo policy | Material đã retired/destroyed và mọi wrapped DEKs đã migrate/xóa hợp lệ |
| **Private signing key** | Có thể cần continuity nếu signer key phải tiếp tục ký; backup đặc biệt nhạy cảm | Key compromise, purpose kết thúc và không còn nhu cầu ký mới; giữ public verification archive riêng |
| **Public verification key/certificate** | Lưu archive để verify chữ ký lịch sử | Hết retention và không còn nghĩa vụ xác minh |
| **HMAC/PSK** | Recovery nếu peers cần tiếp tục xác thực cùng secret | Secret đã rotate và mọi consumer/legacy acceptance đã dừng |
| **TLS/mTLS private key** | Recovery có thể cần để duy trì identity trong DR | Có thể cấp certificate/key mới; không giữ bản sao cũ vô thời hạn |
| **CA root/intermediate key** | Backup offline, quorum/escrow và recovery ceremony | CA đã được thay thế và mọi chain/issuance dependencies đã kết thúc |
| **SSH user key** | Thường có thể tạo lại; private key cá nhân không nên backup tập trung tùy tiện | User credential đã revoke, không còn use case |
| **Recovery shares** | Cần custody/quorum để phục hồi master secret | Scheme/share epoch cũ đã reconstitute và hết dependency |

### 7.1. DEK: thường backup dưới dạng wrapped key

Ứng dụng thường lưu **encrypted DEK** cạnh ciphertext. Điều này giảm việc lưu plaintext DEK, nhưng vẫn cần bảo vệ KEK hoặc recovery path có thể unwrap nó. Nếu encrypted DEK được backup mà KEK bị hủy, ciphertext tương ứng có thể không còn phục hồi được.

### 7.2. KEK: tránh tự tạo một bản raw export thiếu kiểm soát

Với KMS/HSM, ưu tiên cơ chế backup/replication/recovery mà provider hoặc thiết bị hỗ trợ. Nếu export/escrow được policy cho phép, cần **wrapping độc lập, dual control, custody, audit và restore test**. Không giả định mọi managed KMS đều cho export hoặc đều tự backup theo cùng semantics.

### 7.3. Signing keys: public history khác private backup

Public keys/certificates có thể cần lưu lâu để kiểm tra chữ ký lịch sử. Private signing key chỉ nên backup khi có yêu cầu continuity/recovery rõ ràng và cơ chế bảo vệ phù hợp. Nếu private key bị compromise, không restore nó để tiếp tục ký.

## 8. Quyết định backup dựa trên mục đích phục hồi

Mỗi key backup cần trả lời **điều gì sẽ được phục hồi, ai được phục hồi, trong bao lâu và bằng cách nào**.

| Recovery objective | Key material cần thiết | Quyết định |
|---|---|---|
| Phục hồi database encrypted | DEKs qua encrypted DEK + KEK recovery path | Duy trì recovery path trong retention |
| Phục hồi archive cũ | Historical DEK/KEK version hoặc migrated copy | Giữ key archive có kiểm soát |
| Tiếp tục ký dịch vụ sau mất HSM | Signing key recovery theo policy/quorum | Chỉ backup nếu continuity yêu cầu |
| Xác minh chữ ký cũ | Public key/certificate chain và timestamp evidence | Lưu public verification archive |
| Tiếp tục webhook HMAC | Shared secret hiện hành và provisioning path | Backup secret hiện hành nếu cần recovery; retire old |
| Khôi phục root CA | CA private key theo ceremony và quorum | Offline backup đặc biệt bảo vệ |
| Khôi phục SSH cá nhân | Tạo credential mới và cập nhật trust | Thường không cần backup private key người dùng |
| Phục hồi key đã compromise | Không nên tái kích hoạt material compromised | Tạo material mới; forensic copy tách biệt nếu cần |

### 8.1. RPO/RTO không biện minh cho bản sao plaintext

Recovery Point Objective và Recovery Time Objective giúp xác định tần suất backup và tốc độ phục hồi, nhưng không yêu cầu lưu raw key ở nơi tiện nhất. Có thể cải thiện RTO bằng **HSM replica, pre-approved quorum, KMS multi-region hoặc wrapped key recovery** mà vẫn giữ separation of duties.

### 8.2. Đừng backup mọi key “để giảm RTO”

Nếu một key có thể generate lại an toàn và không bảo vệ dữ liệu lịch sử, việc backup có thể không cần thiết. Ví dụ ephemeral session key hoặc key dùng cho một phiên ngắn có thể tạo mới khi kết nối lại; giữ backup của nó làm tăng rủi ro mà không cải thiện recovery đáng kể.

## 9. Chính sách quyết định backup: giữ, tạo mới hay không backup

Không nên dùng một chính sách duy nhất cho mọi loại key. Cần phân loại theo **purpose, exportability, data dependency, recovery objective, compromise state và retention**.

| Điều kiện | Quyết định gợi ý | Lý do |
|---|---|---|
| Key đang active và mất key sẽ dừng dịch vụ nghiêm trọng | Duy trì recovery mechanism được phê duyệt | Đáp ứng availability |
| Key đã ngừng Encrypt nhưng còn ciphertext cần Decrypt | Giữ recovery path cho recipient-use | Dữ liệu lịch sử còn phụ thuộc |
| Key đã được thay và toàn bộ data/backup đã migrate, verify | Lập destruction review; không tạo thêm backup | Không còn mục đích recovery |
| Key ephemeral, có thể tạo lại, không bảo vệ dữ liệu lưu trữ | Không backup | Tạo lại an toàn và ít rủi ro hơn |
| Key bị confirmed compromise | Không tạo operational backup để restore lại | Tránh tái kích hoạt secret bị lộ |
| Signing key đã hết purpose nhưng public verification còn cần | Lưu public key/cert evidence; private backup chỉ khi có nhu cầu riêng | Verify không cần private key |
| Key còn legal hold hoặc retention dependency | Giữ theo policy, giới hạn quyền và thời hạn | Nghĩa vụ lưu trữ chưa kết thúc |
| Inventory/evidence chưa đủ | Chưa kết luận không cần; mở review | Tránh xóa nhầm dependency |

### 9.1. Trạng thái quyết định cần rõ ràng

Một key registry có thể dùng các trạng thái như:

- **BACKUP_REQUIRED:** có recovery objective và dependency được xác định.
- **PROTECTED_RECOVERY_CONFIGURED:** provider/HSM/escrow đã có cơ chế phục hồi được kiểm tra.
- **NO_NEW_BACKUP:** không tạo thêm bản sao; key hiện tại có thể vẫn cần cho operations.
- **RETAIN_EXISTING_FOR_ARCHIVE:** chỉ giữ recovery copy phục vụ Decrypt/Verify lịch sử.
- **DESTRUCTION_REVIEW:** dependency/retention đã có vẻ kết thúc, chờ approval.
- **COMPROMISED_ISOLATED:** không restore operational; evidence được bảo quản theo incident policy.
- **DESTROYED_VERIFIED:** material và các recovery copies thuộc phạm vi đã được xử lý có bằng chứng.

Đây là trạng thái minh họa; tổ chức cần thống nhất semantics với KMS/HSM và hệ thống inventory.

### 9.2. Không dùng “backup exists” như một trạng thái đủ

Cần biết backup **ở đâu, chứa gì, ai có thể restore, phụ thuộc key nào, lần cuối restore thành công khi nào và khi nào phải hủy**. Một file backup tồn tại nhưng không thể mở hoặc không ai có quyền recovery không phải cơ chế DR đáng tin.

## 10. Thiết kế backup key an toàn

Khi thật sự cần recovery, hãy thiết kế bản sao theo nguyên tắc **bảo vệ ít nhất ngang hoặc cao hơn hệ thống đang hoạt động**.

### 10.1. Các yêu cầu cơ bản

- **Encryption at rest:** backup material được bảo vệ bằng cơ chế wrapping/backup phù hợp.
- **Independent trust boundary:** key bảo vệ backup không phụ thuộc vòng lặp vào chính key đang được backup.
- **Access isolation:** chỉ recovery principals được phê duyệt mới truy cập.
- **Separation of duties:** người tạo, người giữ, người phê duyệt và auditor có trách nhiệm riêng.
- **Dual control/quorum:** áp dụng cho master keys, CA keys hoặc recovery material có blast radius lớn.
- **Immutable/append-only audit:** ghi backup, restore, access và destruction.
- **Geographic separation:** có bản recovery ở miền DR theo threat model, nhưng không nhân bản không cần thiết.
- **Integrity verification:** phát hiện backup bị sửa hoặc thiếu dữ liệu.
- **Retention/deletion policy:** xác định thời điểm hết nhu cầu và cách xóa.
- **Restore exercise:** chứng minh quy trình thực sự hoạt động, không chỉ có file.

### 10.2. Tránh vòng phụ thuộc khi wrapping backup

~~~text
KEK-A bảo vệ DEK-A
Backup của KEK-A lại chỉ được mã hóa bằng chính KEK-A
KEK-A mất -> không thể giải mã backup của KEK-A
~~~

Một recovery design cần **root/recovery key độc lập hoặc cơ chế HSM/provider backup** có thể phục hồi mà không cần key đang bị mất. Quan hệ wrapping phải được mô tả trong dependency graph, kiểm tra không tạo vòng lặp và được diễn tập.

### 10.3. Không xuất raw key chỉ để dễ sao lưu

Nếu provider hỗ trợ HSM backup, multi-region replica hoặc key recovery ceremony, ưu tiên cơ chế đó. Nếu policy cho phép export, phải có lý do, wrapping target độc lập, access controls, custody, audit và kế hoạch hủy bản export. **Exportable backup làm tăng đáng kể blast radius** nếu media bị mất.

## 11. KMS và HSM: không giả định semantics backup giống nhau

Managed KMS, cloud HSM, on-premises HSM và software key vault có **cách lưu material, replication, export, deletion và disaster recovery khác nhau**. Một chính sách không nên giả định mọi provider tự backup key material hoặc cho phép restore cùng cách.

### 11.1. Cần xác minh gì từ provider?

| Thuộc tính | Câu hỏi |
|---|---|
| **Material durability** | Provider bảo đảm lưu bền vững trong những miền nào? |
| **Regional scope** | Key chỉ có ở một region hay có replica/multi-region semantics? |
| **Key replication** | Replica dùng cùng material hay material khác? |
| **Exportability** | Raw key có thể export không; dưới điều kiện và quyền nào? |
| **Backup/restore** | Backup được tạo tự động hay phải thao tác; ai có thể restore? |
| **Deletion** | Disable, pending deletion và destroyed khác nhau ra sao? |
| **Recovery identity** | Principal/quorum nào cần để phục hồi? |
| **Audit coverage** | Backup, restore, export, policy changes có được ghi không? |
| **Failure domain** | Provider outage, account suspension, region loss ảnh hưởng thế nào? |
| **Portability** | Có thể phục hồi sang thiết bị/provider khác không, theo chuẩn nào? |

### 11.2. KMS key resource và raw material không phải cùng một thứ

Backup cấu hình key resource, alias, policy hoặc grants **không tự tạo bản backup raw key material**. Ngược lại, có material backup nhưng thiếu policy/permissions, context, key version hoặc application metadata có thể khiến ứng dụng không sử dụng được.

### 11.3. Multi-region không tự động là backup độc lập

Replica có thể chia sẻ control plane, account, billing, administrative identity hoặc provider failure domain. Cần đánh giá **độc lập về sự cố, quyền truy cập và recovery** thay vì chỉ nhìn thấy hai region.

### 11.4. HSM backup cần kiểm soát quorum

Với HSM, backup/restore có thể đòi hỏi backup domain, operator cards, M-of-N shares, secure transport hoặc thiết bị tương thích. Kiểm tra quorum sau khi một custodian nghỉ việc; không để việc giảm số người giữ share làm mất khả năng phục hồi.

## 12. Envelope encryption: lưu wrapped DEK đúng cách

Trong envelope encryption, dữ liệu được mã hóa bằng **DEK**, còn **KEK** bảo vệ DEK. Một record thường lưu:

- Ciphertext payload.
- Nonce/IV và authentication tag theo AEAD.
- AAD schema/context cần để xác thực.
- Encrypted/wrapped DEK.
- KEK reference và material/version metadata.
- Algorithm/format version và object/tenant identity.

~~~mermaid
flowchart TD
    P["Plaintext"] --> E["AEAD Encrypt"]
    D["DEK"] --> E
    E --> C["Ciphertext + nonce + tag"]
    D --> W["Wrap DEK"]
    K["KEK trong KMS/HSM"] --> W
    W --> X["Encrypted DEK"]
    C --> R["Backup record"]
    X --> R
    M["AAD + keyRef + version + format metadata"] --> R
~~~

### 12.1. Backup ciphertext và encrypted DEK cùng revision

Không lưu ciphertext ở revision mới nhưng encrypted DEK ở revision cũ. Dùng **immutable record version, manifest hoặc transaction/CAS** để đảm bảo payload, nonce, tag, AAD, wrapped DEK và key metadata luôn đồng bộ.

### 12.2. KEK recovery là dependency của encrypted DEK

Wrapped DEK không có giá trị phục hồi nếu không còn KEK/material hoặc provider mechanism để unwrap. Key inventory phải liên kết **KEK → encrypted DEKs → objects → backups/archives**.

### 12.3. Không backup plaintext DEK nếu wrapped DEK đáp ứng recovery objective

Nếu hệ thống đã lưu encrypted DEK cạnh ciphertext và KMS/HSM có recovery path đáng tin, việc tạo thêm plaintext DEK backup thường tăng rủi ro mà không cần thiết. Mọi ngoại lệ cần threat model, approval và hạn lưu cụ thể.

### 12.4. Rewrap không thay thế backup của dependency

Khi KEK rotation, có thể rewrap DEK dưới KEK mới; nhưng trước khi retire KEK cũ cần xác minh **mọi encrypted DEK versions, snapshots và archives** đã được xử lý hoặc còn recovery path được chấp thuận.

## 13. Offline backup, immutable storage và split knowledge

Một số material có blast radius lớn như root CA, recovery master hoặc HSM backup domain cần cơ chế backup offline/quorum. Mục tiêu là giảm khả năng attacker đang kiểm soát production có thể truy cập luôn recovery copy.

### 13.1. Các lớp kiểm soát

- **Offline/isolated storage:** không mount liên tục vào production.
- **Immutable retention:** ngăn sửa/xóa trái phép trong thời hạn được phê duyệt.
- **Encryption/wrapping:** backup được bảo vệ bởi root recovery độc lập.
- **M-of-N custody:** nhiều người giữ shares/credentials theo threshold.
- **Geographic separation:** tránh cùng một thảm họa phá hủy cả production và backup.
- **Access ceremony:** restore cần request, approval, operator và audit.
- **Periodic inventory:** kiểm kê bản sao, owner, vị trí và trạng thái.
- **Controlled destruction:** hết retention thì hủy cả bản sao và media theo policy.

### 13.2. Offline không đồng nghĩa an toàn tuyệt đối

Media offline có thể bị đánh cắp, thất lạc, hư hỏng, copy hoặc mở bởi người giữ sai quyền. Cần encryption, tamper evidence, custody log, kiểm kê vật lý và kiểm tra khả năng restore.

### 13.3. Immutability cũng cần thời hạn

Immutable backup giúp chống ransomware/xóa trái phép, nhưng có thể giữ lại key đã hết purpose hoặc compromise. Thiết kế phải có **retention lock có thời hạn, legal hold có phê duyệt và destruction workflow sau khi lock kết thúc**.

### 13.4. Split knowledge và dual control

Không để một người giữ toàn bộ thông tin cần thiết để restore root secret có blast radius lớn. Tuy nhiên, threshold không nên chỉ tồn tại trên giấy: phải kiểm tra shares độc lập, quorum, thay custodian và diễn tập khôi phục thực tế.

## 14. Retention của key backup phải gắn với retention của dữ liệu

Key backup có thể cần tồn tại ít nhất trong khoảng dữ liệu còn cần Decrypt/Verify và có nghĩa vụ phục hồi. Nhưng không phải mọi key phải giữ lâu bằng thời gian hoạt động của doanh nghiệp.

### 14.1. Ma trận thời hạn

| Dữ liệu/key | Yếu tố quyết định retention |
|---|---|
| Database backup encrypted | Backup retention, restore window, legal hold |
| Archive hóa đơn/hợp đồng | Nghĩa vụ lưu trữ và xác minh tính toàn vẹn |
| DEK theo object | Retention của object và mọi bản backup/version |
| KEK bọc DEKs | Tập encrypted DEKs còn phụ thuộc và DR retention |
| Private signing key | Nhu cầu ký mới/continuity; public verification evidence riêng |
| HMAC secret | Thời gian peer/consumer còn chấp nhận và nhu cầu vận hành |
| Root CA key | Thời gian phát hành/chứng thực và recovery policy |
| Ephemeral session key | Thường kết thúc cùng session; không giữ backup sau đó |

### 14.2. Retention của dữ liệu và retention của key không luôn bằng nhau

Nếu dữ liệu đã được re-encrypt hoàn toàn dưới key mới và các bản backup cũ đã hết hạn/xóa, key cũ có thể đủ điều kiện destruction sớm hơn retention của dữ liệu mới. Nếu chỉ archive cũ còn, key lịch sử có thể cần giữ dù ứng dụng không còn tạo dữ liệu dưới nó.

### 14.3. Legal hold cần được thể hiện trong inventory

Một key có thể được giữ vì tranh chấp hoặc điều tra. Legal hold phải có **owner, scope, approval, review date và điều kiện giải phóng**; không nên biến thành ngoại lệ vô thời hạn mà không ai chịu trách nhiệm.

### 14.4. Backup không phải phương án thay cho retention policy

Giữ key vô hạn để có thể phục hồi mọi dữ liệu đã xóa có thể mâu thuẫn với chính sách xóa dữ liệu. Hãy xác định rõ dữ liệu nào cần giữ, key nào cần giữ và khi nào phải kết thúc cả hai.

## 15. Backup và key compromise: không phục hồi lại bí mật đã mất

Backup được thiết kế để phục hồi khi mất/hỏng material, nhưng nếu key đã bị compromise thì restore bản sao đó có thể **tái kích hoạt cùng một lỗ hổng**.

### 15.1. Phân biệt loss với compromise

| Tình huống | Mục tiêu recovery |
|---|---|
| HSM bị hỏng, key chưa bị lộ | Khôi phục cùng material từ backup được bảo vệ nếu policy cho phép |
| Region outage, key còn tin cậy | Failover/restore theo provider recovery mechanism |
| Raw DEK bị lộ | Không restore DEK cũ để dùng tiếp; thay DEK và đánh giá re-encrypt |
| KEK bị lộ | Không tái kích hoạt KEK cũ; tạo KEK mới, đánh giá wrapped DEKs |
| Private signing key bị copy | Không khôi phục để Sign; tạo key pair mới và cập nhật trust |
| HMAC secret bị lộ | Không provision lại old secret cho peers; thay secret |
| Recovery share bị compromise | Reconstitute/re-share hoặc rekey theo scheme; xử lý bản share cũ |

### 15.2. Backup forensic khác backup operational

Trong incident, có thể cần bảo toàn **bằng chứng vật liệu bị compromise** để điều tra. Bản forensic phải được cô lập, hạn chế quyền, đánh dấu rõ và không được dùng như nguồn phục hồi hoạt động. Việc giữ evidence phải tuân theo legal/security policy.

### 15.3. Đừng phục hồi từ backup cũ mà không kiểm tra thời điểm tạo

Một backup có thể được tạo **sau thời điểm attacker đã truy cập**. Khi restore, có thể mang theo key material, credentials, policy hoặc persistence đã bị lộ. Phải xác định recovery point đáng tin và rebuild control plane nếu cần.

### 15.4. Restore có thể tái tạo cả quyền cũ

Backup cấu hình IAM, KMS grants, secret manager policies và CI/CD manifests có thể chứa quyền đã bị thu hồi. Không phục hồi nguyên trạng quyền đó cùng với dữ liệu; phải **reconcile policy hiện tại và deny list** trước khi workload hoạt động.

## 16. Quy trình kiểm kê dependency trước khi ngừng backup

Một quy trình clearance có thể gồm:

1. Xác định **key material identity/version** và trạng thái lifecycle.
2. Liệt kê mọi producer/consumer và operation được phép.
3. Truy vấn ciphertext, encrypted DEK, archive, snapshot, replicas và backup catalog.
4. Liên kết key với data owner, tenant, retention và legal hold.
5. Xác minh re-encryption/rewrap migration đã hoàn tất bằng read-after-write và restore tests.
6. Kiểm tra các consumer offline, đối tác, batch jobs và DR sites.
7. Kiểm tra recovery shares, HSM replicas, provider-managed backup và media copies.
8. Đánh giá khả năng tạo lại key hoặc phục hồi từ nguồn khác nếu bỏ backup.
9. Lập quyết định **NO_NEW_BACKUP / RETAIN / DESTRUCTION_REVIEW**.
10. Lấy approval độc lập, lưu evidence và đặt ngày review/destruction.

### 16.1. Tìm kiếm phải dựa trên material identity

Một alias có thể đổi tên hoặc trỏ tới material version mới. Cần mapping alias, provider key ID, material version/fingerprint nếu provider hỗ trợ, wrapped DEK metadata và import provenance. Không dựa duy nhất vào tên key trong application config.

### 16.2. Đừng chỉ tìm dữ liệu đang online

Các nguồn dễ bị bỏ quên: object versioning, database PITR, snapshots, offline tapes, developer exports, partner copies, staging, analytics lakes, DLQ, test fixtures và legal archives.

### 16.3. Quyết định không backup cần có người chịu trách nhiệm

Key owner/data owner xác nhận dependency; security/key custodian đánh giá material exposure; backup/DR owner xác nhận recovery path; approver độc lập chấp thuận destruction nếu có. Không để một automation job tự suy luận từ tuổi key rồi xóa backup.

## 17. Restore test: chứng minh backup thực sự dùng được

Một bản backup chưa được restore test chỉ là **giả định về khả năng phục hồi**. Kiểm tra file tồn tại hoặc checksum khớp không chứng minh ứng dụng có thể dùng key để phục hồi dữ liệu.

### 17.1. Những gì cần kiểm thử

- Restore ciphertext và metadata từ backup thật trong môi trường cô lập.
- Resolve đúng key ID/material version, không dựa vào alias có thể đã đổi.
- Unwrap encrypted DEK bằng KMS/HSM recovery identity được phê duyệt.
- Decrypt/Verify AEAD với đúng nonce, tag và AAD.
- Verify chữ ký lịch sử với public key/certificate chain đúng thời điểm.
- Kiểm tra tenant/object authorization để không khôi phục dữ liệu sai phạm vi.
- Đo RTO/RPO và ghi các bước cần operator/quorum.
- Kiểm tra audit event, custody và không lộ plaintext key trong output.
- Xác nhận application version/algorithm reader còn tương thích.
- Thử quy trình khi primary region/KMS endpoint không khả dụng nếu DR objective yêu cầu.

### 17.2. Tần suất restore test

Tần suất dựa trên criticality, retention, thay đổi provider, rotation frequency và yêu cầu DR. Một key bảo vệ dữ liệu tài chính nhiều năm cần mức kiểm tra khác key ephemeral. **Sau khi đổi KEK, thay HSM, thay quorum hoặc migration backup**, nên có test phù hợp trước khi retire recovery path cũ.

### 17.3. Test restore không được làm lộ key

Sử dụng recovery role riêng, môi trường cách ly, dữ liệu mẫu không nhạy cảm nếu có thể và output chỉ chứa kết quả/metadata. Không dump raw DEK/KEK để xác nhận bằng mắt.

### 17.4. Restore test cũng kiểm tra dependency graph

Nếu chỉ có thể restore khi một operator duy nhất đăng nhập hoặc một alias cũ còn tồn tại, đó là dấu hiệu dependency chưa được quản lý tốt. Ghi lại mọi thủ tục thủ công và giảm single-person dependency.

## 18. Hủy backup và crypto-shredding khi key hết nhu cầu

Khi không còn mục tiêu recovery hợp lệ, tổ chức cần xử lý **cả material, backup copies, wrapped copies, replicas, shares và metadata có thể kích hoạt restore** theo policy.

### 18.1. Những bản sao cần xét

- Backup export trong vault/escrow.
- HSM backup media và replica.
- Recovery shares, smartcards, operator credentials.
- Snapshot/VM image/backup catalog có chứa plaintext secret.
- Encrypted key blobs còn có thể unwrap bằng key khác.
- Secret manager versions và cache/replication.
- Offline tapes, archive, DR site và bản sao đối tác.
- Forensic copy có legal hold hoặc retention riêng.

### 18.2. Không nhầm xóa metadata với xóa key

Xóa alias hoặc key record có thể chỉ làm mất reference. Cần provider/HSM confirmation cho material destruction, kiểm tra replica/recovery semantics và giữ evidence. Nếu backup media immutable, có thể phải đợi retention lock kết thúc hoặc áp dụng quy trình crypto-shredding đã được phê duyệt.

### 18.3. Crypto-shredding có điều kiện

Crypto-shredding dựa trên việc hủy mọi material/recovery path đủ để giải mã dữ liệu. Nếu có raw key copy ở ngoài miền kiểm soát, không thể tuyên bố ciphertext đã không thể giải mã chỉ vì KMS key bị Destroyed.

### 18.4. Destruction phải có dual control với key quan trọng

Với KEK dùng chung, root CA hoặc recovery master, destruction cần dependency clearance, independent approval, provider readback và evidence. Không cho cùng một actor tạo backup rồi tự phê duyệt xóa backup của chính mình.

### 18.5. Sau destruction, không tạo lại backup từ snapshot cũ

Backup catalog hoặc DR snapshot cũ có thể được restore sau destruction và vô tình đưa key material đã hết hiệu lực trở lại. Cần **tombstone/deny list, version floor hoặc restore reconciliation** để loại bỏ material đã destroyed/compromised sau mọi lần restore.

## 19. Key inventory và backup registry

Không thể quyết định backup nào còn cần thiết nếu tổ chức không biết **key nào tồn tại, đang bảo vệ dữ liệu gì, nằm ở đâu và ai chịu trách nhiệm**.

| Thuộc tính | Nội dung |
|---|---|
| **Key identity** | Provider key ID, material version, alias mapping, provenance |
| **Purpose/type** | DEK, KEK, signing, HMAC, CA, recovery, ephemeral |
| **Owner/custodian** | Data owner, key owner, recovery custodian, approver |
| **Algorithm/usage** | Algorithm, key size, Encrypt/Decrypt/Sign/Verify/Wrap permissions |
| **Lifecycle state** | Active, decrypt-only, retired, revoked, pending destruction, destroyed |
| **Dependencies** | Ciphertexts, wrapped DEKs, archives, certificates, child keys |
| **Backup locations** | KMS/HSM replica, escrow, offline media, backup IDs |
| **Backup form** | Wrapped material, HSM backup, shares, provider recovery |
| **Recovery objective** | RPO/RTO, datasets/services restored |
| **Retention/hold** | Expiry, legal hold, review date, destruction eligibility |
| **Access controls** | Recovery principals, quorum, SoD, audit references |
| **Last restore test** | Date, result, scope, evidence and unresolved issues |
| **Compromise status** | Trusted, suspected, confirmed, isolated |
| **Destruction evidence** | Provider result, media disposal, replica/escrow clearance |

### 19.1. Không lưu plaintext key trong inventory

Inventory chỉ lưu **metadata và references**. Không thêm raw DEK/KEK/private key, HMAC secret, password hoặc recovery shares vào spreadsheet/CMDB để “dễ quản lý”.

### 19.2. Backup catalog phải biết key dependency

Backup system cần lưu metadata cho biết ciphertext nào phụ thuộc key version nào, encrypted DEK nào cần KEK nào, và recovery procedure nào áp dụng. Nếu backup catalog không thể liên kết data với key material, việc hết retention hoặc phục hồi sẽ dễ sai.

### 19.3. Đồng bộ trạng thái sau rotation và destruction

Khi rotate/rewrap/re-encrypt, registry phải phản ánh material version mới và old dependencies còn lại. Khi destroy, ghi trạng thái provider đã xác nhận và ngăn snapshot restore tái kích hoạt material cũ.

## 20. Quy trình vận hành: từ tạo backup đến ngừng backup

### 20.1. Khi phê duyệt một backup mới

1. Ghi recovery objective, data owner, key owner và retention.
2. Chứng minh key không thể tạo lại hoặc việc tạo lại không đáp ứng RTO/RPO.
3. Chọn cơ chế KMS/HSM/escrow phù hợp, tránh plaintext export không cần thiết.
4. Xác định root wrapping/recovery độc lập và quorum.
5. Cấp recovery identity theo least privilege.
6. Ghi backup location, version, material identity và custody.
7. Chạy restore test trong môi trường kiểm soát.
8. Đặt ngày review và destruction condition ngay khi tạo.

### 20.2. Khi rà soát backup định kỳ

- Key còn phục vụ Encrypt/Sign mới hay chỉ Decrypt/Verify lịch sử?
- Dữ liệu/backup nào vẫn phụ thuộc?
- Recovery test gần nhất có đạt không?
- Có custodian hoặc principal nào đã thay đổi?
- Có bản copy ngoài inventory hoặc backup location đã lỗi thời?
- Key đã bị rotate, revoke, compromise hoặc provider thay đổi semantics?
- Retention/legal hold còn hiệu lực không?
- Có thể giảm số bản sao mà vẫn đạt recovery objective không?

### 20.3. Khi ngừng backup

1. Đóng new backup jobs cho đúng material version.
2. Xác nhận mọi consumer/data dependency và retention.
3. Kiểm tra archive, replicas, offline media và recovery shares.
4. Nếu cần, migrate dữ liệu sang key mới và restore test.
5. Lập destruction review, phê duyệt độc lập.
6. Hủy copies theo policy/provider và lấy evidence.
7. Cập nhật registry, deny list và backup catalog.
8. Kiểm thử restore snapshot cũ không làm key đã destroyed sống lại.
9. Theo dõi old-key use và exceptions đến khi đóng.

### 20.4. Không xóa bản backup đang nằm trong legal hold

Legal hold hoặc nghĩa vụ lưu trữ phải được xác minh với owner có thẩm quyền. Nếu key backup cần giữ để đọc dữ liệu theo hold, giới hạn quyền và mục đích; khi hold được giải phóng, quay lại destruction review thay vì tự động kéo dài vô hạn.

## 21. Java 17: planner đánh giá nhu cầu giữ key backup

Ví dụ dưới đây là **decision planner** thuần. Nó phân loại liệu cần tạo recovery backup, giữ bản hiện tại, ngừng tạo bản mới hay mở destruction review. Code **không gọi KMS/HSM, không xóa key và không thực hiện backup thật**.

Các nguyên tắc được thể hiện:

- Key còn cần Decrypt/Verify hoặc có dependent data thì vẫn cần recovery path.
- Key compromised không được khôi phục operational từ backup cũ.
- Key destroyed không tạo backup mới.
- Nếu chưa hết retention hoặc có legal hold thì không được kết luận đủ điều kiện destruction.
- Nếu recovery đã được cấu hình và kiểm thử, không tự tạo thêm bản sao dư thừa.
- Quyết định destructive luôn cần review/approval độc lập.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class KeyBackupPlanner {
    public enum Lifecycle {
        ACTIVE,
        DECRYPT_ONLY,
        VERIFY_ONLY,
        RETIRED,
        REVOKED,
        DESTROYED
    }

    public enum Action {
        CREATE_PROTECTED_RECOVERY_BACKUP,
        VERIFY_EXISTING_RECOVERY,
        RESTORE_TEST_REQUIRED,
        RETAIN_FOR_HISTORICAL_DATA,
        DO_NOT_CREATE_NEW_BACKUP,
        DO_NOT_RESTORE_COMPROMISED_KEY,
        ISOLATE_FORENSIC_EVIDENCE,
        DESTRUCTION_REVIEW,
        BLOCK_DESTRUCTION,
        REQUIRE_INDEPENDENT_APPROVAL
    }

    public record KeyRecord(
        String keyId,
        Lifecycle lifecycle,
        boolean requiredForDecrypt,
        boolean requiredForVerify,
        boolean dependentCiphertextExists,
        boolean legalHold,
        boolean retentionExpired,
        boolean compromised,
        boolean recoveryRequired,
        boolean protectedRecoveryConfigured,
        boolean restoreTestPassed
    ) {}

    public record Plan(
        String keyId,
        Set<Action> actions
    ) {}

    public static Plan evaluate(KeyRecord key) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(key.keyId());
        Objects.requireNonNull(key.lifecycle());

        if (key.keyId().isBlank()) {
            throw new IllegalArgumentException("Missing key ID");
        }

        EnumSet<Action> actions = EnumSet.noneOf(Action.class);

        if (key.lifecycle() == Lifecycle.DESTROYED) {
            actions.add(Action.DO_NOT_CREATE_NEW_BACKUP);
            return new Plan(key.keyId(), Set.copyOf(actions));
        }

        if (key.compromised()) {
            actions.add(Action.DO_NOT_RESTORE_COMPROMISED_KEY);
            actions.add(Action.DO_NOT_CREATE_NEW_BACKUP);
            actions.add(Action.ISOLATE_FORENSIC_EVIDENCE);
            actions.add(Action.REQUIRE_INDEPENDENT_APPROVAL);
            if (key.requiredForDecrypt() || key.requiredForVerify()
                    || key.dependentCiphertextExists()
                    || key.legalHold() || !key.retentionExpired()) {
                actions.add(Action.BLOCK_DESTRUCTION);
            }
            return new Plan(key.keyId(), Set.copyOf(actions));
        }

        boolean historicalDependency =
            key.requiredForDecrypt()
            || key.requiredForVerify()
            || key.dependentCiphertextExists();

        boolean retentionBlocked =
            !key.retentionExpired() || key.legalHold();

        boolean activePurpose = key.lifecycle() == Lifecycle.ACTIVE;

        if (historicalDependency) {
            actions.add(Action.RETAIN_FOR_HISTORICAL_DATA);
        }

        if (key.recoveryRequired()) {
            if (key.protectedRecoveryConfigured()) {
                actions.add(Action.VERIFY_EXISTING_RECOVERY);
                actions.add(Action.DO_NOT_CREATE_NEW_BACKUP);
                if (!key.restoreTestPassed()) {
                    actions.add(Action.RESTORE_TEST_REQUIRED);
                }
            } else {
                actions.add(Action.CREATE_PROTECTED_RECOVERY_BACKUP);
            }
        } else {
            actions.add(Action.DO_NOT_CREATE_NEW_BACKUP);
        }

        if (activePurpose || retentionBlocked || historicalDependency) {
            actions.add(Action.BLOCK_DESTRUCTION);
        } else {
            actions.add(Action.DESTRUCTION_REVIEW);
            actions.add(Action.REQUIRE_INDEPENDENT_APPROVAL);
        }

        return new Plan(key.keyId(), Set.copyOf(actions));
    }

    public static void main(String[] args) {
        KeyRecord archiveKey = new KeyRecord(
            "archive-dek-v4",
            Lifecycle.DECRYPT_ONLY,
            true,
            false,
            true,
            false,
            false,
            false,
            true,
            true,
            true
        );

        Plan plan = evaluate(archiveKey);
        System.out.println(plan.keyId());
        System.out.println(plan.actions());
        // Chỉ in metadata/action; không in key bytes.
    }
}
~~~

### 21.1. Cách đọc kết quả planner

- **CREATE_PROTECTED_RECOVERY_BACKUP:** recovery objective có nhưng chưa có cơ chế recovery được cấu hình.
- **VERIFY_EXISTING_RECOVERY:** đã có recovery mechanism; cần kiểm tra khả năng dùng, không tạo thêm bản sao tự động.
- **RESTORE_TEST_REQUIRED:** recovery mechanism đã cấu hình nhưng chưa có bằng chứng restore test đạt.
- **RETAIN_FOR_HISTORICAL_DATA:** vẫn còn Decrypt/Verify hoặc ciphertext dependency.
- **DO_NOT_CREATE_NEW_BACKUP:** không có lý do tạo bản sao mới hoặc key đã destroyed/compromised.
- **DO_NOT_RESTORE_COMPROMISED_KEY:** không đưa material bị lộ trở lại production.
- **DESTRUCTION_REVIEW:** đủ điều kiện xem xét hủy, chưa có nghĩa đã được phép xóa.
- **BLOCK_DESTRUCTION:** còn legal hold, retention hoặc dependency.

### 21.2. Giới hạn của ví dụ

Planner chỉ dùng dữ liệu được truyền vào; nó không chứng minh inventory đầy đủ, không biết provider-specific backup semantics và không thể phát hiện raw key copy nằm ngoài hệ thống. Production cần nguồn inventory đáng tin, approval workflow, audit, provider readback, restore evidence và xử lý trạng thái unknown. **Không dùng boolean thiếu dữ liệu như false để suy ra không còn dependency**; cần trạng thái UNKNOWN riêng trong hệ thống thực tế.

### 21.3. Vì sao planner không tự xóa backup?

Key backup có thể là bản phục hồi duy nhất cho archive hoặc DR. Destruction cần kiểm tra dependency graph, legal hold, retention, restore và provider semantics. Code minh họa chỉ đưa ra review actions; một executor riêng cần least privilege và dual control.

## 22. Workflow trạng thái backup và destruction

Một workflow có thể phân tách **đề nghị backup, cấu hình recovery, xác minh restore, ngừng tạo bản mới và hủy copies**.

~~~mermaid
stateDiagram-v2
    [*] --> INVENTORIED: Key material registered
    INVENTORIED --> NEED_ASSESSED: Recovery objective reviewed
    NEED_ASSESSED --> BACKUP_APPROVED: Backup is justified
    NEED_ASSESSED --> NO_NEW_BACKUP: No recovery need
    BACKUP_APPROVED --> RECOVERY_CONFIGURED: KMS/HSM/escrow configured
    RECOVERY_CONFIGURED --> RESTORE_VERIFIED: Restore test passed
    RESTORE_VERIFIED --> RETAINED: Retention/review active
    RETAINED --> DEPENDENCY_REVIEW: Key retired or data migrated
    DEPENDENCY_REVIEW --> RETAINED: Dependency remains
    DEPENDENCY_REVIEW --> DESTRUCTION_APPROVED: Dependencies cleared
    DESTRUCTION_APPROVED --> DESTROYED_VERIFIED: Provider/media evidence
    NO_NEW_BACKUP --> DEPENDENCY_REVIEW
    DESTROYED_VERIFIED --> [*]
~~~

### 22.1. Trạng thái phải có ý nghĩa cụ thể

- **INVENTORIED:** material, owner, purpose và dependencies được định danh.
- **NEED_ASSESSED:** recovery objective và retention đã được đánh giá.
- **BACKUP_APPROVED:** có mục đích hợp lệ và approval.
- **RECOVERY_CONFIGURED:** cơ chế provider/HSM/escrow đã được cấu hình.
- **RESTORE_VERIFIED:** restore test đạt với evidence.
- **RETAINED:** bản sao đang nằm trong retention/hold được phê duyệt.
- **NO_NEW_BACKUP:** không tạo thêm copy; key có thể vẫn cần hoạt động.
- **DEPENDENCY_REVIEW:** xác minh mọi data/consumer/backup đã kết thúc.
- **DESTRUCTION_APPROVED:** owner/approver cho phép hủy.
- **DESTROYED_VERIFIED:** provider/media evidence xác nhận material trong scope đã được xử lý.

### 22.2. Idempotency và trạng thái không đồng bộ

Backup jobs, provider API và deletion workflows có thể timeout hoặc được retry. Dùng **backup ID, key material version, operation ID và state revision**; readback trước khi lặp. Không coi timeout là thất bại để tạo bản sao mới vô hạn hoặc coi HTTP success là provider đã destroy.

### 22.3. Restore phải tôn trọng tombstone

Nếu một key đã destroyed/compromised, restore snapshot cũ không được tự động khôi phục nó thành active. Duy trì **deny list/tombstone/version floor** ngoài snapshot có thể rollback; áp dụng trước khi workload nhận key.

## 23. Audit và bằng chứng backup lifecycle

Một quyết định backup/no-backup cần có thể giải thích được sau này.

### 23.1. Audit record minh họa

~~~json
{
  "changeId": "key-backup-review-042",
  "keyRef": "archive-dek-v4",
  "materialVersion": "v4",
  "decision": "RETAIN_EXISTING_FOR_ARCHIVE",
  "reason": "HISTORICAL_CIPHERTEXT_DEPENDENCY",
  "dataScope": "billing-archive-2024",
  "recoveryMethod": "KMS_UNWRAP_VIA_APPROVED_ROLE",
  "approvedBy": "key-owner-17",
  "verifiedBy": "dr-auditor-03",
  "lastRestoreTest": "2026-10-12T09:30:00Z",
  "reviewAt": "2027-04-12T00:00:00Z"
}
~~~

Đây là schema minh họa, không phải format chuẩn của KMS provider. Không ghi plaintext key, recovery share, bearer token hoặc dữ liệu nghiệp vụ nhạy cảm vào audit.

### 23.2. Evidence cần giữ

- Key inventory/material version và owner.
- Recovery objective, data dependency và retention/hold.
- Backup mechanism, location, access policy và custody.
- Approval và separation of duties.
- Restore test result, RTO/RPO và các bước thủ công.
- Provider state, backup/replica identifiers và audit references.
- Dependency clearance, destruction request và provider confirmation.
- Residual risk, evidence gap và ngày review tiếp theo.

### 23.3. Audit không được chứa chính secret cần bảo vệ

Audit nên ghi **reference, operation, actor, result và evidence ID**. Nếu ghi raw key để “chứng minh đúng key”, audit trở thành một kho secret thứ hai có rủi ro lớn.

## 24. Case studies

### 24.1. Case A — DEK đã retire nhưng archive còn thời hạn

Một hệ thống billing chuyển từ DEK-A sang DEK-B. Dữ liệu hiện hành đã được mã hóa bằng DEK-B, nhưng snapshot và archive hóa đơn cũ vẫn lưu ciphertext dưới DEK-A.

**Quyết định đúng:**

1. Không tạo thêm plaintext DEK-A backup nếu encrypted DEK và KEK recovery path đã đáp ứng policy.
2. Giữ recovery path cần thiết cho DEK-A trong thời gian archive còn phụ thuộc.
3. Gắn DEK-A ở trạng thái decrypt-only, chặn Encrypt mới.
4. Restore test một mẫu archive từ backup thật.
5. Theo dõi retention, legal hold và bản archive còn tồn tại.
6. Khi archive hết hạn hoặc đã re-encrypt/migrate và verify, mở destruction review.

**Bài học:** Key không còn dùng để Encrypt mới vẫn có thể cần cho Decrypt lịch sử; không backup thêm không đồng nghĩa xóa recovery path đang cần.

### 24.2. Case B — Ephemeral session key bị backup trong VM image

Một nhóm đóng gói VM image chứa snapshot process memory và cấu hình session key tạm thời. Key chỉ phục vụ một phiên kết nối đã kết thúc nhưng bản image được lưu lâu dài.

**Rủi ro:**

- Secret không còn mục đích vẫn tồn tại trong image.
- Người có quyền đọc image có thể lấy key/session state.
- Restore image có thể tái sử dụng credential cũ hoặc trạng thái không an toàn.

**Xử lý:**

1. Ngừng tạo image chứa memory/secret không cần thiết.
2. Rebuild image sạch và tạo session key mới khi workload khởi động.
3. Rà soát image copies, registries, snapshots và access logs.
4. Hủy image chứa secret theo retention/policy sau khi xác minh dependencies.
5. Bổ sung kiểm tra để loại secret, token và volatile key khỏi golden image.

**Bài học:** Key ephemeral thường nên tạo lại theo phiên; backup của nó có thể chỉ kéo dài rủi ro.

### 24.3. Case C — KEK có recovery backup nhưng không ai kiểm tra restore

Một doanh nghiệp có backup HSM được lưu offline nhiều năm. Custodian thay đổi, thiết bị HSM đời cũ ngừng hỗ trợ và chưa từng diễn tập restore.

**Rủi ro:**

- Backup tồn tại nhưng không còn thiết bị/quorum tương thích.
- Recovery shares có thể thiếu hoặc người giữ không còn quyền.
- Archive encrypted DEKs không thể Unwrap khi thảm họa.

**Xử lý:**

1. Kiểm kê backup domain, media, shares, operator credentials và device compatibility.
2. Bổ nhiệm custodians, xác minh threshold/quorum và dual control.
3. Thực hiện restore exercise trong lab/DR theo policy.
4. Nếu không restore được, lập kế hoạch migration/recovery khi key còn hoạt động.
5. Chỉ retire recovery path cũ sau khi replacement đã được kiểm thử.
6. Đặt lịch test và review khi tạo backup mới.

**Bài học:** Backup không có restore evidence không bảo đảm availability.

### 24.4. Case D — Key đã compromise bị phục hồi từ backup cũ

Một signing key bị lộ, tổ chức đã tạo key pair mới và cập nhật verifier. Sau đó một DR restore phục hồi VM snapshot cũ, trong đó có private key cũ và cấu hình signer cũ.

**Xử lý:**

1. Duy trì tombstone/deny list cho old key material và old key ID.
2. Áp dụng policy hiện tại sau restore, trước khi signer được phép hoạt động.
3. Revoke old Sign permission và kiểm tra verifier trust.
4. Xóa old private material khỏi image/snapshot theo incident policy và retention.
5. Test DR restore không tái kích hoạt old signing key.
6. Giữ public verification evidence lịch sử riêng nếu cần.

**Bài học:** Recovery có thể vô tình khôi phục compromise nếu snapshot không được reconcile với trạng thái security mới.

## 25. Ma trận kiểm thử backup và recovery

| Tình huống | Kết quả mong đợi |
|---|---|
| Key active có recovery objective được duyệt | Recovery mechanism được cấu hình và restore test |
| Key ephemeral đã hết session | Không tạo backup operational mới |
| DEK retired nhưng archive còn tồn tại | Giữ recovery path để Decrypt lịch sử |
| DEK đã re-encrypt mọi data và backups | Dependency review xác nhận trước destruction |
| KEK còn bọc encrypted DEKs trong snapshot | Không xóa backup/recovery path của KEK |
| KEK alias đổi nhưng material giữ nguyên | Inventory giữ mapping và không nhầm thành key mới |
| KEK mới đã rewrap live data nhưng archive cũ chưa migrate | Old recovery dependency vẫn được ghi nhận |
| Private signing key hết purpose | Public verification archive được xử lý riêng; private backup theo continuity need |
| Signing private key bị compromise | Không restore bản operational cũ |
| Public certificate cần Verify lịch sử | Lưu public evidence theo retention |
| HMAC secret đã rotate, consumers còn old acceptance | Không xóa recovery material trước khi cutover, nhưng đặt cutoff |
| HMAC old secret bị compromise | Không provision lại old secret như key hoạt động |
| KMS config backup không chứa key material | Không coi config backup là key backup |
| Provider managed KMS có replication | Xác minh scope/failure domain, không mặc định là independent backup |
| HSM backup media không có quorum | Restore test fail, remediation được mở |
| Recovery share holder rời tổ chức | Quorum/custody được cập nhật và diễn tập |
| Backup wrapping key phụ thuộc chính key được backup | Dependency cycle được phát hiện và thiết kế lại |
| Plaintext DEK được đưa vào database dump | Security validation fail |
| Immutable backup chứa key đã compromise | Cô lập evidence, không restore operational |
| Legal hold còn hiệu lực | Destruction bị block, có owner/review date |
| Retention hết nhưng archive vẫn có bản sao | Dependency scan tìm đủ mọi copy trước clearance |
| Không tìm thấy dependency do inventory thiếu | Trạng thái UNKNOWN, không tự kết luận NO_DEPENDENCY |
| Restore ciphertext từ backup | Decrypt/Verify thành công với đúng key version/AAD |
| Restore nhầm key alias đã đổi | Version pinning/provider ID phát hiện sai |
| Restore test chỉ kiểm tra checksum | Không được coi là end-to-end recovery test |
| Restore role là một admin duy nhất | SoD/single-person dependency được ghi nhận và xử lý |
| Backup bị sửa | Integrity check phát hiện và restore không dùng dữ liệu lỗi |
| Backup copy nằm ngoài inventory | Mở incident/remediation, không tuyên bố destruction hoàn tất |
| Backup retention lock chưa hết | Chờ policy/legal clearance trước xóa |
| Key destroyed nhưng snapshot cũ còn | Tombstone/deny list ngăn restore key thành active |
| DR restore phục hồi credential đã revoke | Reconcile current policy trước khi bật workload |
| Duplicate backup job | Idempotency ngăn tạo nhiều bản sao không cần |
| Provider API timeout lúc backup | Readback/reconcile trước khi retry |
| Provider API báo ScheduleDeletion | Chưa báo Destroyed nếu chưa có confirmation |
| Destruction request thiếu approval | Workflow từ chối |
| Backup forensic của compromised key | Cô lập, label, access log; không operational restore |
| Backup root CA key | Offline custody/quorum và restore ceremony được kiểm thử |
| RPO/RTO thay đổi | Review lại recovery mechanism và số bản sao cần thiết |
| Key rotation hoàn tất | Inventory, backup catalog và dependency versions được đồng bộ |
| Không còn mục tiêu recovery | Không tạo backup mới; mở destruction review theo policy |

### 25.1. Positive tests và negative tests

**Positive tests** xác nhận người có thẩm quyền có thể phục hồi đúng dữ liệu, đúng tenant, đúng key version trong RTO/RPO đã duyệt.

**Negative tests** xác nhận principal không được phép không thể đọc backup, restore key, lấy recovery shares, sửa audit hoặc đưa material đã destroyed/compromised trở lại hoạt động.

Không dùng raw production key để thử nghiệm hoặc in secret ra logs. Dùng test keys, dữ liệu không nhạy cảm, canary recovery identities và môi trường được phê duyệt.

## 26. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Backup tất cả keys theo mặc định | Attack surface và retention tăng | Chứng minh recovery objective cho từng key |
| Không backup key nào để giảm rủi ro | Mất khả năng phục hồi dữ liệu lịch sử | Giữ recovery path có kiểm soát cho dependencies |
| Xóa backup vì key đã retired | Archive không còn Decrypt được | Phân biệt originator-use và recipient-use |
| Giữ backup vô thời hạn | Key cũ tiếp tục mở dữ liệu không còn mục đích | Retention và destruction review |
| Backup plaintext DEK trong DB dump | Bản sao secret lan rộng | Lưu wrapped DEK và bảo vệ KEK |
| Mã hóa backup KEK bằng chính KEK đó | Không thể khôi phục khi mất KEK | Root recovery độc lập, không có wrapping cycle |
| Coi KMS config backup là material backup | Có policy nhưng không có key để phục hồi | Xác minh provider backup semantics |
| Coi multi-region replica là backup độc lập | Chung account/control plane vẫn có thể bị sự cố | Đánh giá failure domain và access separation |
| Không restore test | Backup có thể không dùng được | Diễn tập định kỳ và sau migration |
| Giữ private signing key backup sau compromise | Có thể tái kích hoạt khả năng ký giả | Cô lập forensic copy, không operational restore |
| Rewrap DEK đã lộ rồi kết luận an toàn | Attacker vẫn có DEK cũ | Thay DEK và đánh giá re-encrypt |
| Hủy KEK khi encrypted DEK còn phụ thuộc | Mất dữ liệu vĩnh viễn | Dependency graph và restore clearance |
| Chỉ xóa alias để gọi là destruction | Material/replicas có thể còn | Provider confirmation và evidence |
| Không kiểm kê offline tapes/exports | Backup copy bị bỏ sót | Inventory toàn bộ media và recipients |
| Một người vừa giữ shares vừa tự duyệt restore | Mất separation of duties | Quorum và independent approval |
| Immutable backup không có expiry | Key compromise được lưu bất khả xóa | Retention lock có thời hạn và hold review |
| Restore snapshot cũ mà không reconcile policy | Credential/key đã revoke được hồi sinh | Tombstone/version floor trước khi chạy workload |
| Dùng boolean false cho dependency không biết | Xóa nhầm backup duy nhất | Trạng thái UNKNOWN và evidence review |
| Chỉ kiểm tra checksum | Không chứng minh Decrypt/Verify thành công | End-to-end restore test |
| Không ghi last restore test | Không biết recovery path còn hoạt động | Backup registry có ngày và evidence |
| Backup forensic bị dùng lại production | Tái đưa secret compromise vào hoạt động | Isolation và labeling bắt buộc |
| Không xét legal hold | Xóa material cần cho nghĩa vụ pháp lý | Hold owner và clearance |
| Giữ key backup để phục hồi dữ liệu đã bị xóa | Có thể mâu thuẫn data retention/deletion policy | Đồng bộ retention của data và key |
| Backup key không có owner | Không ai chịu trách nhiệm review/destruction | Gán owner, custodian, approver |
| Backup job retry tạo nhiều bản sao | Tăng số secret copies và chi phí | Idempotency theo key version/backup ID |

## 27. Câu hỏi tự kiểm tra

**Câu 1. Nguyên tắc “không backup key không còn cần thiết” có nghĩa là không backup bất kỳ key nào đã retired không?**

**Trả lời:** Không. Key retired có thể vẫn cần Decrypt/Verify archive hoặc backup lịch sử. Chỉ ngừng backup khi dependency và retention đã được clearance.

**Câu 2. Vì sao backup mọi key có thể làm tăng rủi ro?**

**Trả lời:** Mỗi bản sao tạo thêm nơi attacker có thể lấy secret, thêm quyền/custody cần bảo vệ và làm việc thu hồi/destruction khó hơn.

**Câu 3. Encrypted DEK có phải plaintext key backup không?**

**Trả lời:** Không. Nó là DEK đã được wrap, nhưng vẫn phụ thuộc KEK hoặc recovery mechanism có thể unwrap.

**Câu 4. Backup ciphertext có đủ để khôi phục dữ liệu không?**

**Trả lời:** Không nếu thiếu encrypted DEK, KEK/recovery path, nonce/tag/AAD và metadata cần thiết.

**Câu 5. Backup KMS alias và policy có khôi phục được raw key material không?**

**Trả lời:** Không mặc nhiên. Configuration/metadata backup khác với backup hoặc replication của material; phải xác minh semantics provider.

**Câu 6. Key đã ngừng Encrypt mới có thể vẫn cần backup không?**

**Trả lời:** Có. Nó có thể còn cần Decrypt/Verify dữ liệu lịch sử, archive hoặc snapshot trong retention.

**Câu 7. Vì sao không nên backup plaintext DEK nếu wrapped DEK đã đáp ứng recovery?**

**Trả lời:** Plaintext copy tạo thêm một secret có thể bị lấy offline, trong khi wrapped DEK cùng KEK recovery path đã đủ cho mục tiêu.

**Câu 8. KEK backup cần độc lập với key nào?**

**Trả lời:** Recovery wrapping/root mechanism không được tạo vòng phụ thuộc chỉ có thể giải mã bằng chính KEK đang được backup.

**Câu 9. Multi-region KMS có tự động là backup độc lập không?**

**Trả lời:** Không. Replica có thể chung account, control plane, administrator và provider failure domain; cần đánh giá độc lập.

**Câu 10. Vì sao HSM backup cần quorum và restore test?**

**Trả lời:** Vì thiếu operator cards/shares, thiết bị tương thích hoặc threshold có thể làm backup không phục hồi được dù media vẫn tồn tại.

**Câu 11. Legal hold ảnh hưởng quyết định xóa key backup như thế nào?**

**Trả lời:** Nếu key cần để truy cập dữ liệu trong hold, destruction phải bị chặn hoặc được xử lý theo phê duyệt/retention tương ứng.

**Câu 12. Backup forensic của key đã compromise có được restore production không?**

**Trả lời:** Không. Nó chỉ được bảo toàn cho điều tra trong miền cô lập; không dùng để khôi phục operations.

**Câu 13. Tại sao phải kiểm tra backup được tạo trước hay sau thời điểm compromise?**

**Trả lời:** Backup sau thời điểm attacker đã truy cập có thể chứa key, credentials hoặc policy đã bị lộ/thay đổi.

**Câu 14. Vì sao restore test cần thử Decrypt/Verify thật?**

**Trả lời:** Checksum chỉ chứng minh bytes không đổi; nó không chứng minh key, metadata, AAD, provider permissions và application reader có thể phục hồi dữ liệu.

**Câu 15. Khi nào có thể mở destruction review?**

**Trả lời:** Khi mọi producer/consumer, ciphertext/archive, backup, replica, legal hold và recovery window đã được xử lý, có evidence và approval.

**Câu 16. Xóa key alias có phải crypto-shredding không?**

**Trả lời:** Không. Alias/reference có thể biến mất trong khi material và các recovery copies vẫn tồn tại.

**Câu 17. Crypto-shredding có bảo đảm nếu attacker đã copy raw key không?**

**Trả lời:** Không. Destroy tại provider không xóa bản copy nằm ngoài miền kiểm soát.

**Câu 18. Vì sao snapshot cũ có thể làm key đã destroyed sống lại?**

**Trả lời:** Snapshot có thể chứa material/config cũ. Restore phải áp dụng tombstone/deny list và trạng thái security mới trước khi workload hoạt động.

**Câu 19. Có nên dùng boolean false khi không biết key còn dependency hay không?**

**Trả lời:** Không. Unknown phải là trạng thái riêng; thiếu bằng chứng không chứng minh không còn dependency.

**Câu 20. Một backup được xem là có ích khi nào?**

**Trả lời:** Khi có mục tiêu recovery được duyệt, được bảo vệ, có owner/custody, còn trong retention và đã chứng minh restore được bằng test phù hợp.

## 28. Checklist triển khai “Không backup key không còn cần thiết”

Trước khi tạo, giữ hoặc xóa một key backup, xác nhận:

- **Purpose:** key phục vụ Encrypt, Decrypt, Sign, Verify, HMAC, CA, recovery hay session nào?
- **Material identity:** provider key ID, material version, alias mapping và provenance có rõ?
- **Dependency:** ciphertext, wrapped DEK, archive, snapshot, replicas, offline media và partners đã được liệt kê?
- **Recipient-use:** key đã ngừng Encrypt nhưng còn cần Decrypt/Verify lịch sử?
- **Recovery objective:** RPO/RTO, service/data scope và owner đã được phê duyệt?
- **Regeneration:** key có thể tạo lại an toàn hay cần giữ material cũ để đọc dữ liệu?
- **Backup form:** wrapped material, HSM backup, replica, escrow hay shares; có tránh plaintext copy không?
- **Root recovery:** wrapping/recovery key độc lập, không có dependency cycle?
- **Provider semantics:** KMS/HSM backup, replication, export, deletion và restore đã được xác minh?
- **Access:** recovery principals, least privilege, dual control, quorum và SoD có rõ?
- **Location:** mọi bản backup, media, snapshots, exports và replicas có trong inventory?
- **Retention:** backup có expiry, review date, legal hold owner và destruction condition?
- **Restore test:** đã kiểm tra Decrypt/Verify thật, RTO/RPO và audit?
- **Compromise:** key đã lộ có bị đánh dấu isolated và cấm operational restore?
- **Rotation:** rewrap/re-encrypt đã cập nhật đúng key version, nonce, tag, AAD và metadata?
- **Migration:** mọi consumers/offline jobs/DR sites đã cutover hoặc có exception được duyệt?
- **Destruction:** dependency clearance, legal hold, independent approval và provider evidence có đủ?
- **Snapshot restore:** tombstone/deny list ngăn material đã destroyed/compromised quay lại?
- **Audit:** ghi backup/restore/decision/destruction events mà không chứa raw secrets?
- **Ownership:** key owner, data owner, custodian, backup/DR owner và approver được phân công?
- **Unknowns:** mọi evidence gap được ghi rõ, không suy thành no-dependency?
- **Closure:** trạng thái registry, backup catalog, monitoring và ngày review tiếp theo đã cập nhật?

## 29. Cây quyết định: có nên tiếp tục giữ backup của key này?

~~~mermaid
flowchart TD
    A["Xác định key material/version"] --> B{"Key đã compromised?"}
    B -->|Có| C["Không restore operational; cô lập forensic evidence"]
    B -->|Không| D{"Còn Encrypt/Sign mới?"}
    D -->|Có| E["Đánh giá recovery objective và backup protection"]
    D -->|Không| F{"Còn Decrypt/Verify hoặc data dependency?"}
    F -->|Có| G["Giữ recovery path cần thiết cho historical use"]
    F -->|Không| H{"Retention/legal hold/DR window còn?"}
    H -->|Có| I["Giữ theo scope, owner và thời hạn"]
    H -->|Không| J["Dependency clearance + independent approval"]
    J --> K["Destruction review và provider/media evidence"]
    E --> L["Restore test + periodic review"]
    G --> L
    I --> L
    C --> M["New material + data/trust migration"]
~~~

Cây quyết định là hướng dẫn phân loại. Nếu dữ liệu đầu vào **unknown**, dừng ở bước review và bổ sung evidence; không tự chọn nhánh “không còn dependency”. Nếu key bị compromise, có thể vẫn phải bảo toàn forensic evidence hoặc migration access trong phạm vi kiểm soát, nhưng không biến bản forensic thành recovery key hoạt động.

## 30. Kết luận

**Không backup key không còn cần thiết** là nguyên tắc giảm số bản sao secret và giới hạn thời gian tồn tại của vật liệu khóa. Nó không có nghĩa xóa mọi key đã retired. Một DEK có thể còn cần cho archive; KEK có thể còn bọc encrypted DEKs; public key có thể cần để Verify chữ ký lịch sử; root CA hoặc recovery material có thể cần backup offline theo quorum.

Quyết định đúng phải dựa trên **purpose, key material identity, originator/recipient-use, dependency graph, retention/legal hold và recovery objective**. Backup thật sự cần thiết phải được bảo vệ bằng KMS/HSM, wrapping độc lập, least privilege, dual control, inventory và restore test. Khi dependency kết thúc, cần ngừng tạo bản mới, rà soát mọi bản copy, xin approval và hủy theo provider/media evidence. Khi key đã compromise, không restore nó để tiếp tục hoạt động; forensic preservation phải tách khỏi operational recovery.

Kết hợp **key lifecycle, DEK/KEK, envelope encryption, KMS/HSM, backup/DR, cryptoperiod, retention, audit, separation of duties và crypto-shredding** để vừa phục hồi được dữ liệu hợp lệ vừa tránh lưu giữ những bản sao khóa không còn mục đích.
