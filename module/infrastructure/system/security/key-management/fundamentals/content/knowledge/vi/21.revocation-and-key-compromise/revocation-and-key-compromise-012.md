# Forensics sau compromise — Điều tra pháp chứng khi khóa mật mã bị xâm phạm

## 1. Forensics sau key compromise là gì?

**Forensics sau compromise** là quá trình **thu thập, bảo toàn, đối chiếu và phân tích bằng chứng** nhằm xác định một sự cố liên quan đến khóa mật mã đã xảy ra như thế nào, kéo dài bao lâu, đối tượng nào có thể bị ảnh hưởng và những biện pháp khắc phục đã thực sự có hiệu lực hay chưa. Mục tiêu không chỉ là tìm nguyên nhân kỹ thuật; kết quả còn phải đủ rõ để **chủ sở hữu dữ liệu, đội Incident Response (IR), KMS/HSM administrators, kiểm toán và các bên có thẩm quyền** ra quyết định về containment, rotation, revocation, re-encryption, restoration và lưu hồ sơ.

Ví dụ: hệ thống hóa đơn dùng **AES-GCM DEK** được bọc bằng **KMS KEK**. Một security alert cho thấy IAM principal của Billing Service gọi thao tác Unwrap bất thường. Câu hỏi điều tra phải tách bạch:

- Principal có bị chiếm không, và trong khoảng thời gian nào?
- Có những thao tác Unwrap nào **thành công**, cho key reference và context nào?
- KMS đã trả **plaintext DEK** cho workload hay thực hiện phép toán hoàn toàn bên trong boundary?
- Workload có thể truy cập **ciphertext của tenant nào**? Có bằng chứng tải/đọc dữ liệu?
- Raw KEK trong KMS có bị export không, hay chỉ là **lạm dụng quyền API**?
- Các quyền đã bị thu hồi thực tế chưa? DEK/key version nào còn được sử dụng và dữ liệu nào cần xử lý?

Nếu chỉ viết trong báo cáo rằng “KMS key compromised, đã rotate”, người đọc sẽ không biết **vật liệu nào bị lộ, tác động thực tế và các giả định còn chưa được kiểm chứng**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề thuộc chương **Revocation và compromise**. Bài học liên kết vòng đời khóa từ sinh, cấp phát, lưu trữ, sử dụng, rotation đến thu hồi/hủy với **mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và audit**.

> **Nguyên tắc:** Bảo toàn chứng cứ **không được tạo thêm đường rò khóa**. Hãy thu thập metadata và artifact có kiểm soát, giảm tối đa việc sao chép plaintext key. Đồng thời, forensic preservation **không phải lý do trì hoãn vô hạn việc ngăn lạm dụng đang diễn ra**.

### 1.1. Kết quả forensics nên trả lời điều gì?

| Câu hỏi | Kết quả mong đợi |
| --- | --- |
| **What?** | Loại sự cố: raw key exposure, unauthorized key use, public-trust tampering, nonce/RNG failure... |
| **Which key?** | Key ID, version/material, algorithm, purpose, owner, environment |
| **Who?** | Principal, workload, actor/role và bằng chứng danh tính có độ tin cậy xác định |
| **When?** | Timeline gồm thời gian xảy ra, phát hiện, containment, cutover và recovery |
| **Where?** | Host/process, KMS/HSM resource, region, account, secret store, backup hoặc partner |
| **How?** | Đường tấn công có chứng cứ: IAM grant, CI artifact, heap dump, secret log, JWKS tampering... |
| **Impact?** | Dữ liệu, wrapped DEKs, tokens, chữ ký, phiên, tenants và relying parties bị ảnh hưởng |
| **Evidence?** | Artifact nguồn, integrity hash, provenance, khả năng kiểm chứng và những khoảng trống |
| **Remediation?** | Quyền đã bị chặn, key mới, migration, trust propagation, DR validation |
| **Residual risk?** | Những bản sao/khả năng đọc hoặc ký giả không thể chứng minh đã loại bỏ |

### 1.2. Khác nhau giữa incident response và forensics

**Incident response** ưu tiên **dừng tổn hại tiếp diễn và phục hồi dịch vụ an toàn**. **Forensics** ưu tiên **chứng minh điều gì có thể đã xảy ra, dựa trên dữ kiện nào**. Chúng bổ trợ nhau nhưng có thể xung đột thời điểm: chặn workload lập tức có thể làm mất volatile evidence; tiếp tục giữ workload hoạt động có thể tạo thêm chữ ký giả hoặc lộ dữ liệu.

Cách thực tế là **IR commander quyết định theo rủi ro**: thu thập nhanh volatile evidence nếu an toàn và được cho phép, đồng thời khóa credentials, grants hoặc network paths khi cần. Không đưa một checklist “phải dump toàn bộ RAM rồi mới revoke key” thành quy tắc tuyệt đối.

## 2. Phân loại đối tượng và mức độ bằng chứng

**Key compromise** là một nhãn sự cố rộng. Forensics phải xác định **vật liệu khóa bị lấy**, **khả năng thao tác bị lạm dụng**, hay **nguồn tin cậy công khai bị giả mạo**.

| Kết luận/giả thuyết | Bằng chứng điển hình | Không được suy diễn |
| --- | --- | --- |
| **Raw secret key exposure** | Plaintext DEK, KEK, HMAC hoặc private key có mặt ở vị trí/người không được phép | Chưa chắc attacker đã có mọi ciphertext liên quan |
| **KMS/HSM key-use abuse** | Sign, Decrypt, Unwrap, GenerateDataKey được gọi ngoài phê duyệt | Không tự kết luận raw KEK/private signing key đã rời HSM |
| **Credential/IAM compromise** | Token/session/principal bị chiếm, grants bị thay | Chưa chắc tất cả key resources của account bị lộ material |
| **Public key/trust compromise** | JWKS, CA certificate, truststore, fingerprint hoặc registry bị tráo | Không tự kết luận private key gốc bị trích xuất |
| **Weak generation** | DRBG/seed lỗi, provenance không đạt, khóa dự đoán được | Không phải key nào cũng đã bị attacker đoán; cần khoanh batch |
| **Cryptographic misuse** | Nonce AES-GCM tái sử dụng, ECDSA nonce yếu, algorithm downgrade | Có thể mất bí mật/toàn vẹn mà không hề lộ raw key |
| **Suspected compromise** | Telemetry và quyền truy cập bất thường, chưa xác nhận output | Không báo confirmed khi chưa đủ chứng cứ |
| **Availability/destructive abuse** | Disable/DeleteKey trái phép, xóa grants, mất material | Không đồng nghĩa data confidentiality đã bị phá |

### 2.1. Phân biệt “confirmed”, “probable”, “possible” và “unknown”

Một hồ sơ nên ghi **mức độ chắc chắn cùng căn cứ**, thay vì một cờ compromised=true:

- **Confirmed:** Có bằng chứng trực tiếp đáng tin cho mệnh đề cụ thể, chẳng hạn plaintext key đã xuất hiện trong artifact ngoài boundary hoặc KMS logs ghi Sign thành công.
- **Probable:** Nhiều tín hiệu độc lập phù hợp cùng một giả thuyết; vẫn còn khả năng khác cần xét.
- **Possible:** Đường tấn công tồn tại hoặc dữ liệu nằm trong vùng truy cập, nhưng chưa có chứng cứ hoạt động xảy ra.
- **Unknown/Not established:** Chưa có dữ liệu đủ tin để kết luận; **không được viết là không xảy ra**.

Ví dụ, việc tìm thấy **plaintext DEK trong logfile** xác nhận DEK đã được ghi ra log. Nó **không nhất thiết xác nhận một người ngoài đã đọc log**; cần thêm evidence về access/exports, retention và bản sao. Ngược lại, không có access log **không chứng minh không ai đọc** nếu logging bị tắt hoặc mất.

### 2.2. Khả năng và hành động là hai tầng riêng

Forensics cần phân biệt:

1. **Capability:** Attacker có thể Decrypt/Sign/Unwrap vì có raw key hoặc quyền API.
2. **Observed action:** Có log/sự kiện cho thấy một operation thành công.
3. **Observed outcome:** Ciphertext/DEK/plaintext/token đã được trả hoặc được sử dụng ở đâu.
4. **Downstream impact:** Dữ liệu thực sự bị đọc, thông điệp giả được chấp nhận, giao dịch phát sinh.

Mỗi tầng cần **evidence và giới hạn kết luận**. Một KMS Decrypt thành công có thể chứng minh dịch vụ đã thực hiện operation, nhưng không tự chứng minh attacker đã đọc nội dung trả về nếu không biết endpoint và đường lấy output.

### 2.3. Public key không phải secret

Đọc public verification key từ JWKS không phải key leak. Tuy nhiên, việc **thay nguồn JWKS được verifier tin** có thể khiến token được ký bởi key của attacker được chấp nhận. Pháp chứng phải điều tra **trust-store/issuer configuration, change history, fetch/caching behavior và tokens**; không chỉ tìm private key file.

## 3. Các nguyên tắc pháp chứng số áp dụng cho key material

### 3.1. Tính nguyên vẹn và provenance

Một bằng chứng đáng tin cần:

- **Nguồn gốc:** Artifact được tạo bởi host, account, service, logging system hoặc người nào; thu lúc nào và bằng phương pháp nào?
- **Integrity:** Hash mạnh của **artifact đã thu thập** (ví dụ SHA-256), lưu cùng metadata và kiểm soát chỉnh sửa.
- **Chain of custody:** Ai có quyền giữ/xem/chuyển artifact, vào thời điểm nào, bản gốc và bản làm việc ở đâu?
- **Repeatability:** Người được ủy quyền có thể kiểm tra lại những truy vấn, parser, phiên bản tool và kết quả nào?
- **Confidentiality:** Artifact có thể chứa raw secrets, tokens, PII hoặc thông tin nhạy cảm; phải được phân loại và hạn chế truy cập.

**SHA-256 hash không tự chứng minh nguồn gốc hoặc thời điểm artifact được tạo.** Nó hỗ trợ phát hiện thay đổi khi so sánh với bản ghi hash đáng tin, nhưng hash do chính attacker gửi cùng artifact **không phải bằng chứng độc lập**.

### 3.2. Bản gốc, bản làm việc và chính sách lưu giữ

Trong phạm vi IR/pháp lý cho phép:

1. Thu thập từ nguồn có thẩm quyền với phương pháp đã được phê duyệt.
2. Ghi **case ID, collector, UTC timestamp, system/region, query/range và collection method**.
3. Tính hash và lưu vào **evidence register** có quyền truy cập hẹp.
4. Bảo vệ bản gốc khỏi chỉnh sửa; phân tích trên **working copy**.
5. Ghi mọi lần chuyển giao, truy cập, lọc, chuẩn hóa hoặc redaction.
6. Đặt retention, legal hold và deletion approval theo quy trình tổ chức.

**Không mở rộng quyền đọc raw secrets cho toàn bộ nhóm điều tra**. Một bản trích xuất log chứa DEK có thể chính là bề mặt rò khóa thứ hai.

### 3.3. Chứng cứ volatile cần quyết định theo rủi ro

Memory, process state, network buffers, ephemeral tokens và in-memory cache có thể mất sau restart. Tuy vậy, **full memory dump** có thể chứa raw DEKs/private keys, credentials và PII, làm tăng đáng kể rủi ro.

Ưu tiên **tối thiểu hóa dữ liệu thu thập**, dùng kỹ thuật và nhân sự forensic được phê duyệt; nếu phải thu full dump thì mã hóa, cách ly, hạn chế copy và audit truy cập. Không hướng dẫn mọi developer tự gửi heap dump chứa secrets vào ticket hoặc chat.

### 3.4. Thời gian có thể lệch

Timeline phải ghi:

- **Event time**: thời điểm hệ thống nguồn cho là sự kiện xảy ra.
- **Ingestion time**: lúc collector/SIEM nhận log.
- **Collection time**: lúc evidence được thu.
- **Effective time**: lúc revoke/cutover thực sự có hiệu lực.

Cần chuẩn hóa **UTC/offset**, theo dõi clock skew, timezone/DST, mức chính xác và source clock. Log đến muộn không đồng nghĩa sự kiện xảy ra muộn. Một timestamp trong payload do attacker tự ký **không phải trusted timestamp** độc lập.

## 4. Preflight forensic: quyết định phạm vi và quyền thu thập

Trước khi thao tác với evidence, mở một **incident case** với trách nhiệm rõ:

| Trường | Ví dụ | Lý do |
| --- | --- | --- |
| **Case/incident ID** | INC-KEY-2026-042 | Nhóm các artifacts và quyết định |
| **Incident commander** | Vai trò IR được ủy quyền | Quyết định containment và escalation |
| **Key inventory reference** | billing-kek-v3 | Không dựa vào alias hoặc key name mơ hồ |
| **Allegation/hypothesis** | Unwrap API bị lạm dụng | Tách giả thuyết khỏi kết luận |
| **Legal/compliance flags** | Retention, legal hold theo chính sách | Tránh hủy chứng cứ/vi phạm nghĩa vụ |
| **Data owner & KMS owner** | Phụ trách dữ liệu và khóa | Phê duyệt truy vấn/migration |
| **Collection scope** | Account/region/host, khoảng thời gian | Giảm tràn dữ liệu và chi phí |
| **Access roles** | Forensic collector, reviewer, approver | Separation of duties |
| **Containment decision** | Suspend principal; preserve logs | Không trì hoãn xử lý rủi ro |

### 4.1. Câu hỏi trước khi xem bất kỳ secret nào

- Có thật sự cần **raw key bytes** để kết luận không? Hầu hết điều tra bắt đầu với **metadata/log references**, không phải bản secret.
- Chứng cứ nằm ở KMS/HSM, IAM, secret store, process logs hay backup?
- Ai có quyền hợp lệ để thu, và thao tác có gây thay đổi trạng thái hoặc làm lộ plaintext không?
- Có thể lấy **provider audit event/opaque key ID/hash của artifact** thay vì ExportKey không?
- Có dữ liệu của tenant khác bị kéo vào phạm vi thu thập không?

Không thử giải mã dữ liệu khách hàng trên diện rộng chỉ để “xem compromised key có mở được không”. Mọi thử nghiệm phải có **ủy quyền, scope và nhật ký**.

### 4.2. Preservation versus containment

Một KMS role đang bị lạm dụng có thể tạo thêm decrypted data trong từng giây. **Tạm khóa grants/credentials** thường cần ưu tiên, song nên ghi nhận **policy/grants state trước và sau** từ nguồn audit khi khả thi. Nếu cần snapshot, không để quy trình chụp chứng cứ kéo dài việc chặn hành vi nguy hiểm.

**Destruction key chưa phải bước forensic đầu tiên**. Hủy sớm có thể ngăn khôi phục dữ liệu hoặc mất metadata hữu ích; đồng thời **không thu hồi raw key attacker đã lấy**. Phân biệt disable/revoke, rotate và destroy.

## 5. Nguồn bằng chứng: thu gì, tránh thu gì?

| Nguồn | Những gì có thể hữu ích | Hạn chế/cảnh báo |
| --- | --- | --- |
| **KMS/HSM audit logs** | Key ID, version/resource, operation, principal, thời gian, kết quả, context metadata | Không phải mọi provider ghi mọi output/raw key; log có thể trễ/thiếu |
| **IAM/STS/identity logs** | Assume role, session issuance, grants, policy modifications, sign-ins | Danh tính token không nhất thiết chỉ ra người thật |
| **Secret manager** | Secret version access, rotation, policy changes | ReadSecret có thể trả plaintext cho caller; tránh truy vấn thực làm lộ |
| **Application logs/traces** | Request/tenant/record IDs, permission decisions, correlation IDs | Logs có thể chứa PII hoặc secret; không tin toàn bộ timestamp |
| **CI/CD & code history** | Secret injection/export, image artifacts, pipeline runs, provenance | Lịch sử Git/artifact còn bản copy dù đã xóa dòng secret |
| **Endpoint/host** | Process/user/session activity, file accesses, dump metadata | Thu memory/files phải có thẩm quyền và bảo vệ material |
| **Database/object store** | Key references, encrypted data keys, ciphertext inventory, object versions | Không mặc định tải toàn bộ plaintext data |
| **PKI/JWKS/truststores** | Issuer, key fingerprints, certificate chains, CRL/OCSP/trust updates | Cache và relying parties có thể chưa áp dụng |
| **Network/proxy/egress** | Destinations, volume, mTLS identities, unusual data flow | Không mặc định suy ra nội dung nếu encrypted |
| **Backup/DR** | Old key versions, grants, wrapped DEKs, snapshots và restore test | Backup cũ có thể hồi sinh revoked material/trust |
| **Third parties** | Partner receipt, API logs, acknowledgement, certificate state | Có độ trễ và khả năng quan sát không đầy đủ |

### 5.1. Tránh tạo thêm bí mật trong quá trình thu thập

Không dùng **Decrypt, Unwrap, Sign hoặc ExportKey** chỉ để tạo một sự kiện “kiểm tra” mà không có nhu cầu và phê duyệt. Một thao tác Unwrap được forensic team kích hoạt có thể làm timeline nhiễu và tạo bản DEK mới trong bộ nhớ.

Khi cần test **principal cũ đã bị chặn**, ưu tiên **negative test có phê duyệt**, dữ liệu test hoặc metadata/permission evaluation theo khả năng provider. Không đưa raw key thật ra terminal để chứng minh nó còn tồn tại.

### 5.2. Các nguồn bằng chứng không có tính tuyệt đối

KMS logging thường ghi metadata operation, nhưng **không bảo đảm mọi plaintext được trả ra đã bị attacker tải hay lưu lại**. Network egress logs cho thấy luồng dữ liệu, nhưng không nhất thiết chỉ ra loại plaintext trong kênh TLS. Trái lại, không có egress bất thường **không loại trừ** việc attacker đọc dữ liệu trong cùng tenant/account.

Kết luận cần dựa trên **corroboration giữa nhiều nguồn**, mô tả coverage và khoảng trống quan sát.

## 6. Lập timeline: sự kiện, trạng thái và mức chắc chắn

### 6.1. Một timeline forensic có cấu trúc

~~~text
2026-11-20T01:05:00Z  [CONFIRMED] Role analytics-prod được cấp Unwrap grant mới
2026-11-20T01:12:00Z  [CONFIRMED] KMS Unwrap thành công với key billing-kek-v3
2026-11-20T01:15:00Z  [OBSERVED] Ứng dụng đọc 12 record references
2026-11-20T01:20:00Z  [UNKNOWN]  Chưa có bằng chứng đáng tin về exfiltration
2026-11-20T01:30:00Z  [CONFIRMED] IR vô hiệu hóa grants và credentials
2026-11-20T01:34:00Z  [VERIFIED] Negative test không còn Unwrap được
2026-11-20T02:10:00Z  [OBSERVED] Writers chuyển Encrypt mới sang DEK v2
~~~

**Timeline trên là giả định phục vụ học tập, không phải log từ một hệ thống có thật.** Chú ý phân biệt **observed event, confirmed fact, hypothesis và unknown**; “chưa thấy exfiltration” không phải “không có exfiltration”.

### 6.2. Gắn evidence ID cho mỗi mệnh đề

Mỗi dòng timeline nên tham chiếu đến:

- **evidenceId**: bản trích xuất hoặc artifact nào hỗ trợ?
- **sourceEventId**: event gốc từ provider, không chỉ log text do app tự tạo.
- **eventTimeUTC, ingestedAtUTC, collectionTimeUTC** và clock uncertainty.
- **source system / account / region / log retention window**.
- **parser/query version** và điều kiện lọc.
- **confidence & alternative explanations** nếu có.

Một conclusion có thể được hỗ trợ bởi nhiều artifacts; ghi liên kết rõ. Khi một source được bổ sung hoặc phát hiện không đáng tin, có thể cập nhật kết luận mà không xóa lịch sử reasoning đã được phê duyệt.

### 6.3. Điều tra độ lệch đồng hồ và log gaps

Ví dụ KMS audit ghi event lúc 01:12 UTC, application trace 08:13 giờ địa phương và proxy log nhập hệ thống lúc 01:20 UTC. Không vội kết luận proxy xử lý trễ tám phút; cần chuẩn hóa timezone, kiểm tra **clock offset, ingestion delay, buffering, logging failures và sampling**.

Nếu SIEM chỉ giữ log 7 ngày nhưng incident phát hiện sau 30 ngày, ghi rõ **earliest observable event** không phải **actual first malicious event**.

## 7. Forensics cho DEK, KEK và envelope encryption

### 7.1. Quan hệ dữ liệu cần truy vết

~~~mermaid
flowchart TB
    E["Evidence: KMS event / secret exposure / IAM change"] --> K["Key ID, material version,<br/>operation, principal, interval"]
    K --> W["KEK reference + wrapped DEK blobs"]
    W --> D["DEK scope: per record, batch hoặc tenant"]
    D --> C["Ciphertext & AAD/context dependencies"]
    C --> B["Backup, object versions, DR replicas"]
    B --> IMP["Data exposure assessment & remediation"]
    K --> IR["Contain IAM/KMS key-use paths"]
    IR --> IMP
~~~

Nếu sự cố ảnh hưởng **raw DEK**, phạm vi trực tiếp là ciphertext được mã hóa dưới DEK ấy. Nếu ảnh hưởng **raw KEK**, cần đi theo **wrapped DEKs** mà attacker có thể tiếp cận. Nếu chỉ lạm dụng KMS Decrypt/Unwrap, cần xem **ciphertext blobs thực tế được gửi**, grants và output đã tới những workloads nào.

### 7.2. Không suy luận từ tên alias

Một alias **billing-current-kek** có thể đã chuyển từ material-v2 sang v3. Trong forensics, không truy vấn chỉ bằng alias hiện tại rồi kết luận những records trong quá khứ dùng v3. Cần:

1. Truy vết lịch sử **alias → key resource/material version** theo mốc thời gian.
2. Kiểm tra **encrypted data key blob metadata** theo provider.
3. Đối chiếu **key ID/version** được application lưu khi Encrypt/Wrap.
4. Kiểm kê **rewrap migrations**, retries và một phần dữ liệu chưa chuyển.
5. Thử **authorized readback** trên mẫu dữ liệu được phép, không dump key.

### 7.3. Sự khác biệt giữa rewrap và re-encrypt ảnh hưởng forensic

~~~text
Trước rotation:
  C_old = AEAD_Encrypt(DEK_A, P, nonce_A, AAD)
  W_old = Wrap(KEK_v1, DEK_A)

Sau rewrap:
  C_old giữ nguyên
  W_new = Wrap(KEK_v2, DEK_A)

Sau re-encrypt:
  C_new = AEAD_Encrypt(DEK_B, P, nonce_B, AAD_new)
  W_B = Wrap(KEK_active, DEK_B)
~~~

Nếu **DEK_A đã lộ**, rewrap W_old sang W_new **không loại bỏ quyền giải mã C_old** của attacker có DEK_A. Nếu **KEK_v1 đã lộ**, rewrap những blobs hiện tại vẫn không thu hồi được bản W_old mà attacker có thể đã sao chép.

Vì vậy báo cáo phải phân biệt **new-write cutover**, **wrapped DEK migration**, **payload re-encryption**, **historical snapshot remediation** và những gì không thể thu hồi.

### 7.4. Cần chứng cứ gì khi khẳng định raw key bị lộ?

| Tình huống | Có thể xác nhận | Cần điều tra thêm |
| --- | --- | --- |
| Plaintext DEK trong application log | Một bản DEK tồn tại ở log | Ai có quyền đọc, ai đã đọc, nơi log được export |
| KMS Decrypt response có thể trả plaintext DEK | API design cho phép workload nhận DEK | Log có operation thành công không, output đi đâu |
| Wrapped DEK bị lấy từ database | Encrypted key blobs bị tiếp cận | Attacker có KEK/Unwrap permission hoặc lỗi crypto khác không |
| KEK ở HSM non-exportable | Provider hạn chế raw export theo thiết kế | Admin/API abuse, import/backup provenance, side channels theo threat model |
| DEK trong memory dump | Secret có trong memory artifact | Dump ai có quyền tải, nơi backup/forensic copy tồn tại |

**Không nhân bản raw key để so sánh** giữa các environments khi chưa được phê duyệt. Nhiều câu hỏi có thể giải bằng key references, version metadata, controlled equality checks hoặc tài liệu provenance.

### 7.5. AEAD nonce reuse là vấn đề khác raw-key theft

Nếu AES-GCM dùng lại nonce dưới cùng DEK, có thể gây tổn hại nghiêm trọng đến confidentiality/integrity theo điều kiện sử dụng, dù **raw DEK chưa từng xuất khỏi hệ thống**. Forensics cần kiểm tra **key identity, nonce allocation, ciphertext metadata, concurrency và usage count**, không chỉ IAM logs.

Một phép thống kê nonce collision chỉ có giá trị khi biết **đúng phạm vi DEK**. Hai records dùng cùng nonce nhưng **khác DEK** không tự chứng minh reuse dưới cùng key.

## 8. Forensics cho signing keys, tokens và chữ ký lịch sử

### 8.1. Private material exposure versus signing oracle

| Chứng cứ | Điều có thể kết luận |
| --- | --- |
| Private signing key xuất hiện ngoài boundary | Rủi ro attacker có thể ký **ngoài** KMS/HSM |
| KMS Sign call trái phép, private key vẫn non-exportable | Có **unauthorized signing activity**, chưa đủ kết luận raw private material bị lấy |
| JWT có signature Verify=true nhưng signer không phê duyệt | Chữ ký hợp lệ về toán học, có thể giả mạo qua key/API/trust path |
| JWKS bị thay public key | Verifier có thể chấp nhận attacker key dù private key gốc chưa lộ |
| Certificate bị revoke | Chính sách trust thay đổi; có thể vẫn còn caching/offline clients |

### 8.2. Điều tra chữ ký và key trust

Đối với một token hoặc chứng từ nghi ngờ:

1. Giữ **original signed bytes**, signature bytes và protected header/manifest theo phạm vi được phép.
2. Xác định **issuer, key ID/version, algorithm, public key fingerprint** từ nguồn tin cậy tại thời điểm.
3. Kiểm tra **Sign event hoặc signing service audit**: principal, operation time, key, request/document ID và policy decision.
4. Đối chiếu **business authorization**: lệnh thanh toán, hóa đơn, release approval có thực sự được cấp quyền?
5. Xem **JWT issuer/audience/exp/nbf**, document domain, certificate KeyUsage/EKU, revocation và token/session state.
6. Xác minh **relying party có chấp nhận** token/chữ ký hay chỉ có một signature được tạo?
7. Đối chiếu **trusted timestamp** khi cần xác định chữ ký có thể đã tồn tại trước lúc key bị lộ.

**Verify=true không chứng minh sự kiện nghiệp vụ hợp lệ.** Nó chỉ là một kết quả kiểm tra mật mã với public key và message bytes đã chọn.

### 8.3. Timestamp trong signed payload không phải trusted timestamp

Nếu attacker có raw private key, họ có thể tạo chữ ký cho message ghi **signedAt là một ngày trong quá khứ**. Điều đó không chứng minh chữ ký thực sự được tạo ngày ấy. Với chữ ký có yêu cầu bằng chứng dài hạn, có thể cần **timestamp authority, revocation evidence, audit logs bất biến và quy trình pháp lý** tương ứng.

Không tự kết luận mọi chữ ký v1 trước ngày compromise đều giả, cũng không chấp nhận mọi chữ ký v1 chỉ vì public Verify thành công.

### 8.4. Phạm vi consumers và cache

Key rotation có thể tạo public-v2 trong JWKS, nhưng một verifier còn **cache public-v1** hoặc không kiểm tra revocation vẫn có thể nhận token v1. Điều tra phải thống kê:

- Những **issuer/clients/regions/partners** nào tin key-v1?
- Mốc **last fetch, cache expiry, JWKS/CRL/OCSP update** và cấu hình client?
- Có **key ID collision/algorithm confusion** giữa các issuers không?
- Revoke trust đã có **negative-test evidence** trên các đường thực tế chưa?

### 8.5. HMAC forensics khác chữ ký số

Nếu webhook HMAC key được chia sẻ giữa hai tổ chức, **bất kỳ bên nào biết secret đều có thể tạo tag đúng**. Một HMAC hợp lệ **không quy trách nhiệm được chỉ từ tag**. Phải đối chiếu ingress logs, mTLS identities, business state, distribution history, timestamps và replay protection.

## 9. Forensics cho KMS/HSM, IAM và secret manager

### 9.1. Bốn bảng thông tin cần đối chiếu

| Nhóm | Các trường trọng yếu |
| --- | --- |
| **Identity** | Principal/session, account/region, source identity, authentication method |
| **Permission** | Role/grant/policy trước-sau sự cố, key resource, operations được phép |
| **Operation** | Timestamp, event ID, key ID, Wrap/Unwrap/Decrypt/Sign/Export, result |
| **Asset** | Ciphertext/data reference, signed object, tenant, key material version |

Lập join bằng **correlation/request ID hoặc những khóa kết nối được xác minh**. Nếu ứng dụng không ghi mapping event → record, không tự điền “tenant A” từ một context string client có thể thao túng.

### 9.2. Những điều audit KMS thường không trả lời trực tiếp

- Plaintext DEK **có được attacker lưu lại** không?
- Một Sign call **có được relying party chấp nhận** hay không?
- Mọi bản sao secret ở **memory, disk, backups và đối tác** đã được phát hiện chưa?
- Đã có exploit **ngoài con đường KMS** hay chưa?
- Public trust change có được mọi client áp dụng ngay không?

Vì vậy kết luận “không thấy event ExportKey” không tự đủ để chứng minh **private key chắc chắn chưa từng rời mọi boundary**, nhất là khi key được sinh/import hoặc backup bằng đường khác.

### 9.3. Admin/policy tampering

Nếu key-admin principal bị chiếm, điều tra lịch sử **CreateKey, ImportKey, Grant, RevokeGrant, DisableKey, ScheduleDeletion, UpdatePolicy và alias changes** tùy API provider. Một thao tác đổi quyền có thể khiến Sign/Decrypt xảy ra sau đó với principal trước đây không được phép.

Giữ **policy snapshots trước/sau**, nhưng tránh ghi raw key material hoặc credential vào report. Không dùng một **live current-policy snapshot** làm chứng cứ duy nhất về policy đã tồn tại ở thời điểm trước.

### 9.4. Secret manager access

ReadSecret thường khác KMS Sign: nó có thể **trả toàn bộ plaintext secret** cho client. Forensics cần xem **secret version, consumer identity, retrieval time, replication/caching, secret rotation và logging**.

Nếu một secret đã được đọc trái phép, revoke quyền ReadSecret có thể ngăn lần đọc tiếp nhưng **không xóa bản plaintext đã nhận**. Phải đánh giá rotation và mọi application dùng secret ấy.

## 10. Phân tích exfiltration và giới hạn khả năng quan sát

### 10.1. Tìm các dấu hiệu phù hợp

Đối với endpoint có thể nhận DEK/plaintext:

- Tương quan **thành công của Unwrap/Decrypt** với data read/export từ ứng dụng.
- Kiểm tra audit của **object store, database, file shares, backup exports**.
- Đối chiếu network egress destination, DNS/proxy và lượng truyền, nếu có và được phép.
- Kiểm tra **process crash dumps, debug logs, tracing collectors và CI artifacts** nhận bản sao.
- Xem **đường truy cập nội bộ** giữa accounts/regions/containers, không chỉ public internet.
- Xác định **logging/telemetry gaps, retention và network visibility**.

### 10.2. Từ volume tới kết luận

Một egress burst 10 GiB không tự chứng minh 10 GiB plaintext đã bị lấy; có thể là ciphertext backup hợp lệ hoặc traffic khác. Một Decrypt thành công không tự chứng minh user trái phép đã đọc dữ liệu. Ngược lại, một attacker có thể lấy secret nhỏ như **32-byte DEK** rồi tải ciphertext ở nguồn khác, nên chỉ nhìn volume mạng sẽ bỏ sót rủi ro.

Nên trình bày:

- **Observed:** Dữ liệu được đo/log với source.
- **Inferred:** Phỏng đoán có lý do dựa trên nhiều quan sát.
- **Unverified:** Cần dữ liệu bổ sung nhưng chưa có.
- **Residual:** Tác động có thể vẫn tồn tại ngay cả sau remediation.

### 10.3. Đừng tạo thêm exfiltration bằng quá trình điều tra

Không tải toàn bộ production database, decrypted records hoặc raw keys về laptop để “test impact” nếu có thể dùng **metadata, controlled queries hoặc môi trường forensic cách ly**. Khi cần dữ liệu mẫu, phải có phê duyệt, phân loại và cơ chế bảo vệ tương ứng.

## 11. Quy trình thực hành forensic theo từng pha

### Pha A — Tiếp nhận và ổn định

1. Tạo **incident ID**, xác định IR commander, key/data owners và kênh liên lạc bảo mật.
2. Viết **initial hypothesis** kèm mức độ chắc chắn; không mặc định key bytes đã lộ.
3. Xác định rủi ro đang hoạt động: token/grant bị chiếm, signer đang tạo giả mạo, logs tiếp tục chứa secret?
4. Quyết định **containment và evidence preservation** với người có thẩm quyền.
5. Ghi nhận trạng thái key/IAM/trust trước-sau thay đổi bằng nguồn audit được bảo vệ.

### Pha B — Thu thập đúng phạm vi

1. Chốt key ID/material version, algorithm, key usage, accounts/regions và khoảng thời gian.
2. Thu **KMS/HSM events** cùng IAM grant/session/policy history.
3. Thu **application and storage access metadata**, correlation IDs và phiên bản deploy.
4. Thu **PKI/JWKS/secret manager history** nếu loại khóa liên quan.
5. Lập evidence register với hash, provenance, collector và access restrictions.
6. Ghi những **nguồn không thể thu** do retention, quyền hoặc hệ thống không hỗ trợ.

### Pha C — Tái dựng

1. Chuẩn hóa timestamp/UTC, sự lệch clock và event ingestion delays.
2. Lập timeline về **who could**, **who called**, **what succeeded** và **what was accessed**.
3. Join KMS operations với data/ciphertext records theo **verified references**, không đoán theo tên alias.
4. Kiểm tra alternate explanations: migration job hợp lệ, rotation bình thường, backup/DR task, log duplication.
5. Tính **blast radius tối đa có cơ sở** và **impact quan sát được**, trình bày hai số/phạm vi riêng.
6. Peer review các kết luận quan trọng với IR, key owner và data owner.

### Pha D — Chữa lỗi và xác minh

1. Thu hồi credential/grant/role hoặc trust bị lạm dụng.
2. Sinh key material mới khi cần, xác định đúng **purpose và boundary**.
3. Rewrap hoặc re-encrypt **đúng mục tiêu**, migrate với readback và policy authorization.
4. Phân phối trusted public keys/revocation tới relying parties; theo dõi cache và offline clients.
5. Chạy **negative tests, affected data readback và DR restore drills**.
6. Đối soát **actual key state** tại KMS/HSM, không chỉ dashboard/application config.

### Pha E — Báo cáo và đóng hồ sơ

1. Ghi **những điều confirmed, probable, possible và unknown**.
2. Ghi timeline, evidence IDs, confidence, alternative explanations và root causes.
3. Tách **containment completed**, **key replacement completed** và **data/trust remediation completed**.
4. Xác định **thông tin còn thiếu, residual risk, owners và thời hạn theo dõi**.
5. Review, phê duyệt, lưu hồ sơ theo policy; chỉ đóng incident theo tiêu chí đã đặt.

~~~mermaid
flowchart TD
    A["Alert/incident intake"] --> B{"Đang có nguy cơ<br/>tiếp diễn?"}
    B -->|"Có"| C["IR containment<br/>revoke grants / block Sign/Unwrap"]
    B -->|"Không rõ"| D["Preserve available evidence<br/>record uncertainty"]
    C --> D
    D --> E["Acquire KMS/IAM/app/PKI/storage<br/>metadata & protected artifacts"]
    E --> F["Chain of custody, hashes,<br/>UTC timeline, source coverage"]
    F --> G["Join key versions + operations<br/>to ciphertext/signatures/tenants"]
    G --> H{"Raw-key exposure,<br/>API abuse hay trust tampering?"}
    H -->|"Raw material"| I["Replacement + data/key material review"]
    H -->|"API abuse"| J["Permission remediation + output review"]
    H -->|"Trust substitution"| K["Restore trust + verifier updates"]
    I --> L["Negative tests, DR/readback,<br/>residual-risk review"]
    J --> L
    K --> L
    L --> M["Evidence-backed report<br/>owner approval / follow-up"]
~~~

**Không xem sơ đồ là quyền tự động phá hủy key hoặc tắt service.** Các hành động thật cần chính sách, trách nhiệm và thẩm quyền tương ứng.

## 12. Mẫu evidence ledger và chain of custody

### 12.1. Schema record minh họa

~~~yaml
# Ví dụ metadata, KHÔNG chứa raw key hoặc bí mật điều tra.
caseId: INC-KEY-2026-042
evidenceId: EV-018
evidenceType: KMS_AUDIT_EXPORT
source:
  system: managed-kms-audit
  accountRef: prod-billing
  region: region-a
  queryReference: Q-KMS-2026-04
  eventTimeWindowUTC:
    start: "2026-11-20T00:00:00Z"
    end: "2026-11-21T00:00:00Z"
collection:
  collectedAtUTC: "2026-11-21T02:00:00Z"
  collectorRole: approved-ir-collector
  method: provider-supported-export
  bytes: 1048576
integrity:
  algorithm: SHA-256
  digestHex: "<actual-hash-computed-from-evidence>"
protection:
  dataClass: restricted
  accessGroup: forensic-case-team
  originalImmutable: true
  retentionPolicyRef: security-evidence-retention
analysis:
  workingCopyReference: EV-018-W1
  parserVersion: audit-parser-v2
  notes: "Coverage and gaps recorded separately"
~~~

Đây là **mẫu tổ chức nội bộ**, không phải chuẩn pháp lý/chứng nhận chung. Cần hiện thực integrity controls ở kho evidence được phê duyệt; viết **originalImmutable=true** trong YAML mà không có cơ chế bảo vệ thực tế **không làm dữ liệu bất biến**.

### 12.2. Một sự kiện truy cập evidence

~~~text
case=INC-KEY-2026-042
evidence=EV-018
at=2026-11-21T03:15:00Z
actor=authorized-forensic-reviewer
action=READ_WORKING_COPY
purpose=KMS_UNWRAP_TIMELINE
approval=CASE-APPROVAL-017
result=ALLOW
~~~

Đừng lưu **access tokens, HSM PIN, decrypted DEK, session cookies hoặc raw credentials** trong ledger. Những references có thể liên kết đến dữ liệu nhạy cảm cũng cần quyền đọc theo vai trò.

### 12.3. Integrity hash không phải authentication

SHA-256 của artifact giúp phát hiện thay đổi nếu so sánh với hash được giữ trong **hệ thống đáng tin cậy**. Hash **không chứng minh collector là ai, log là thật, clock là chính xác hay artifact hợp lệ về pháp lý**. Khi cần tính xác thực nguồn có thể dùng **digitally signed evidence manifest**, attestations hoặc nền tảng log có integrity guarantees phù hợp, kèm verification policy.

Không tự ký một file bằng private key bất kỳ rồi kết luận đó là bằng chứng đáng tin: public verification key, người ký, phạm vi ký và thời điểm phải được xác thực từ **trust source độc lập**.

## 13. Java 17: sắp xếp timeline và phân loại audit events không lộ khóa

Đoạn mã minh họa này dùng **dữ liệu synthetic** đã được giảm nhạy cảm. Nó:

- Kiểm tra mỗi sự kiện có **event ID, key ID, principal, operation, result và Instant UTC**.
- Sắp xếp timeline theo thời gian và event ID để có thứ tự ổn định khi timestamp bằng nhau.
- Đánh dấu những **operation thành công có nguy cơ** để IR review.
- Không suy luận **raw KEK/private key bị xuất** chỉ vì có Decrypt/Sign.
- Không xuất raw key, DEK, plaintext, token hay key bytes.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class KeyForensicTimelineDemo {
    private KeyForensicTimelineDemo() {}

    enum Operation {
        SIGN, DECRYPT, UNWRAP, EXPORT,
        UPDATE_KEY_POLICY, REVOKE_GRANT, OTHER
    }

    enum Outcome {
        SUCCESS, DENIED, ERROR
    }

    record AuditEvent(
            String eventId,
            Instant eventTimeUtc,
            String keyId,
            String principal,
            Operation operation,
            Outcome outcome,
            String sourceEvidenceId
    ) {
        AuditEvent {
            Objects.requireNonNull(eventTimeUtc);
            Objects.requireNonNull(operation);
            Objects.requireNonNull(outcome);
            if (eventId == null || eventId.isBlank()
                    || keyId == null || keyId.isBlank()
                    || principal == null || principal.isBlank()
                    || sourceEvidenceId == null
                    || sourceEvidenceId.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing forensic event metadata");
            }
        }
    }

    static List<AuditEvent> timeline(
            List<AuditEvent> events
    ) {
        // Copy before sorting; original evidence remains untouched.
        List<AuditEvent> ordered = new ArrayList<>(events);
        ordered.sort(Comparator
                .comparing(AuditEvent::eventTimeUtc)
                .thenComparing(AuditEvent::eventId));
        return List.copyOf(ordered);
    }

    static boolean needsSecurityReview(AuditEvent event) {
        if (event.outcome() != Outcome.SUCCESS) {
            return false;
        }
        return Set.of(
                Operation.SIGN, Operation.DECRYPT,
                Operation.UNWRAP, Operation.EXPORT,
                Operation.UPDATE_KEY_POLICY
        ).contains(event.operation());
    }

    public static void main(String[] args) {
        List<AuditEvent> sample = List.of(
                new AuditEvent(
                        "ev-03",
                        Instant.parse("2026-11-20T01:30:00Z"),
                        "billing-kek-v3", "ir-operator",
                        Operation.REVOKE_GRANT,
                        Outcome.SUCCESS, "EV-002"),
                new AuditEvent(
                        "ev-01",
                        Instant.parse("2026-11-20T01:12:00Z"),
                        "billing-kek-v3", "analytics-prod",
                        Operation.UNWRAP,
                        Outcome.SUCCESS, "EV-001"),
                new AuditEvent(
                        "ev-02",
                        Instant.parse("2026-11-20T01:13:00Z"),
                        "billing-kek-v3", "analytics-prod",
                        Operation.UNWRAP,
                        Outcome.DENIED, "EV-001")
        );

        for (AuditEvent event : timeline(sample)) {
            String flag = needsSecurityReview(event)
                    ? "REVIEW_OUTPUT_AND_AUTHORIZATION"
                    : "NO_SUCCESSFUL_CRYPTO_ACTION_IN_THIS_EVENT";
            System.out.printf(
                    "%s | %s | %s | %s | %s%n",
                    event.eventTimeUtc(),
                    event.eventId(),
                    event.operation(),
                    event.outcome(),
                    flag);
        }
    }
}
~~~

Ví dụ đầu ra rút gọn:

~~~text
2026-11-20T01:12:00Z | ev-01 | UNWRAP | SUCCESS | REVIEW_OUTPUT_AND_AUTHORIZATION
2026-11-20T01:13:00Z | ev-02 | UNWRAP | DENIED | NO_SUCCESSFUL_CRYPTO_ACTION_IN_THIS_EVENT
2026-11-20T01:30:00Z | ev-03 | REVOKE_GRANT | SUCCESS | NO_SUCCESSFUL_CRYPTO_ACTION_IN_THIS_EVENT
~~~

### 13.1. Giới hạn về độ tin cậy của ví dụ

1. **Code không truy cập KMS, IAM hay incident files thật**. AuditEvent phải đến từ **export đã được kiểm chứng**, không tin JSON tự khai từ client.
2. **Thành công của Unwrap** chỉ khiến việc xem output/authorization cần ưu tiên; **không xác nhận raw KEK đã lộ**.
3. **KMS Denied event** không đủ chứng minh không có operation thành công ở nguồn khác hoặc thời điểm khác.
4. Thứ tự event dựa trên **reported timestamps**; chưa điều chỉnh clock drift hoặc event-time ambiguity.
5. **Giá trị key ID, principal và event ID** có thể chứa metadata nhạy cảm và cần kiểm soát trong báo cáo.
6. **Các nguồn logs có thể bị trùng hoặc mất**; deduplication chỉ theo event ID khi biết phạm vi uniqueness thật.
7. **Outcome ERROR** có thể vẫn có side effect ở backend tùy API; cần tra semantics provider, không coi mọi ERROR là không có thay đổi.
8. Chưa có **chain-of-custody storage, hashing, access review, peer approval hoặc signature verification**.

### 13.2. Khả năng tái lập kết quả

Trong thực tế, giữ bản evidence gốc, ghi **parser version, query filters, event coverage** và tạo **working copy** có metadata reduction. Khi reviewer chạy lại cùng parser với cùng input đã bảo toàn, kết quả nên thống nhất; nếu khác, phải ghi lý do và không sửa dữ liệu gốc để khớp giả thuyết.

## 14. Java 17: tạo SHA-256 integrity record cho artifact đã được phép thu

Đây là ví dụ **tính fingerprint của artifact**, không phải tính hash của private key để dò hoặc trích xuất key. Nó giả định **bên thu đã có artifact được phép xử lý** và đã kiểm soát nơi lưu trữ.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class ForensicArtifactDigest {
    private ForensicArtifactDigest() {}

    public static String sha256OfAuthorizedArtifact(
            InputStream approvedEvidenceStream
    ) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];
        int n;
        while ((n = approvedEvidenceStream.read(buffer)) != -1) {
            if (n > 0) {
                digest.update(buffer, 0, n);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Lưu ý:

- Function **không mở file tùy ý, không export keys và không upload dữ liệu**. Caller chịu trách nhiệm lấy artifact từ nguồn được phê duyệt.
- Hash phải đi cùng **artifact identity, size, collector, collection time, access logs và storage integrity**.
- Một digest trùng nhau hỗ trợ khẳng định **hai streams bytes giống nhau dưới SHA-256**, không chứng minh source artifact là sự thật.
- Nếu artifact chứa raw secrets, **quyền giữ và truy cập artifact vẫn rất nhạy cảm**, dù digest bản thân không phải plaintext key.
- Không hiển thị nội dung artifact trong log, và không tái sử dụng dòng hash làm bằng chứng nguồn gốc độc lập khi không có trust.

## 15. Correlation và suy luận nhân quả: những bẫy khó thấy

Forensics không chỉ là sắp xếp các dòng log. **KMS audit, application trace, network telemetry và storage events** có semantics riêng, đôi khi có độ trễ hoặc duplicate. Join sai có thể dẫn đến báo nhầm tenant, nhầm dữ liệu hoặc nhầm attacker.

### 15.1. Thiết lập các liên kết có chứng cứ

Ví dụ một ứng dụng ghi:

~~~text
traceId=trace-1001
principal=analytics-prod
recordId=invoice-42
tenantId=tenant-a
kekReference=billing-kek-v3
kmsRequestId=kms-2026-0123
result=UNWRAP_SUCCEEDED
~~~

Và audit KMS ghi:

~~~text
eventId=kms-2026-0123
principal=analytics-prod
keyId=billing-kek-v3
operation=Unwrap
result=SUCCESS
~~~

Khi **kmsRequestId** thật sự là định danh provider/trace được kiểm tra, tương quan có thể đáng tin hơn việc join theo timestamp gần nhất. Nhưng một trường tenantId **do client tự nhập** vẫn chưa chứng minh bản ghi thuộc tenant đó; phải kiểm tra **data ownership từ nguồn độc lập**.

### 15.2. Các nguồn có thể không độc lập

Hai logs cùng được sinh từ một application đã bị chiếm **không nhất thiết là hai bằng chứng độc lập**. Nếu attacker có quyền sửa app logs, nhiều dòng tương tự vẫn có thể mang cùng nguồn giả. Cần ưu tiên **provider-side audit, externally protected collector, immutable event storage hoặc cross-system traces** theo threat model.

### 15.3. Tương quan không chứng minh ý định

Một KMS Decrypt và một database read cùng xảy ra trong một phút **không tự chứng minh dữ liệu đã bị exfiltrate**. Có thể là một backup job hợp lệ. Forensics cần:

1. Kiểm tra identity, job schedule, change request và expected service behavior.
2. Đối chiếu source event IDs và routing.
3. Phân biệt accesses được policy cho phép với **hành vi nghiệp vụ trái phép dù IAM Allow**.
4. Ghi mức chắc chắn, không ép mọi event vào một câu chuyện tấn công duy nhất.

### 15.4. Thiếu log không có nghĩa không có sự kiện

Nguyên nhân log thiếu có thể là **sampling, mất kết nối, log retention, API không hỗ trợ logging, policy cố tình tắt hoặc attacker xóa/sửa logs**. Báo cáo nên nêu **coverage window** và **known gaps** trước mỗi kết luận phủ định.

Ví dụ viết phù hợp: “Không tìm thấy thành công của Unwrap trong các KMS audit records đã thu cho account A, region B, từ T1–T2; không có coverage cho endpoint C trước T1.” Không viết “Không có bất kỳ ai giải bọc khóa” nếu bằng chứng chỉ bao phủ một phần hệ thống.

## 16. Containment và remediation phải để lại bằng chứng riêng

Một phần quan trọng của forensic sau compromise là chứng minh các biện pháp phòng vệ **đã có hiệu lực thực tế**.

### 16.1. Tách các loại completion

| Mốc | Điều cần chứng minh |
| --- | --- |
| **Containment complete** | Principal/đường API nguy hiểm đã bị chặn theo scope |
| **Key replacement complete** | Vật liệu mới được tạo đúng boundary và được dùng cho operation mới |
| **Trust update complete** | Relying parties áp dụng key/trust/revocation policy mới |
| **Data migration complete** | Các records còn cần đã được rewrap hoặc re-encrypt theo mục tiêu |
| **Recovery validated** | Backup/DR restore được dữ liệu hợp lệ, không hồi sinh revoked grants |
| **Forensic review complete** | Timeline, scope, gaps và confidence được review/phê duyệt |
| **Incident closure** | Residual risk, nghĩa vụ theo dõi/thông báo và owners đã được chấp thuận |

Không gộp tất cả thành trạng thái **ROTATED**. Ví dụ key-v2 đã được tạo nhưng một signer ở region khác vẫn ký v1; hoặc application đã re-encrypt production nhưng backup vẫn giữ ciphertext/DEK cũ.

### 16.2. Những kiểm chứng cần ưu tiên

- **KMS/IAM negative test:** Principal cũ có còn Sign/Unwrap/Decrypt không?
- **Actual key usage:** Có event Sign/Wrap/Encrypt mới bằng key-v1 sau cutover không?
- **Ciphertext readback:** Dữ liệu migration mở được bằng key version/AAD mới không?
- **Integrity:** AEAD authentication failures có tăng không, có mismatch metadata/ciphertext?
- **JWKS/PKI trust:** Verifiers ở các regions/partners có còn chấp nhận key bị revoked trái policy không?
- **DR:** Restore snapshot cũ có làm sống lại grant/trust bị thu hồi không?
- **Root-cause regression:** Secret logger, CI artifact export hoặc authorization bug đã được sửa và test chưa?

**Negative test không nên kéo raw private key hoặc DEK production ra ngoài boundary.** Có thể dùng key thử nghiệm với cùng policy hoặc thao tác bị từ chối qua API có phê duyệt, tùy ranh giới và nguy cơ.

### 16.3. KMS/HSM deletion evidence

Một key ở trạng thái **pending deletion** không giống **destroyed**. Một record application ghi status=DELETED cũng không đủ chứng minh key material đã bị hủy ở các replicas, backups hoặc đối tác.

Forensic report nên ghi rõ **backend state, effective timestamp, provider operation reference, protected backup/DR scope và residual copies**. Nếu không thể xác minh mọi bản sao, ghi giới hạn thay vì báo “khóa không còn tồn tại ở đâu”.

## 17. Backup/DR, hủy khóa và pháp chứng dài hạn

### 17.1. Vấn đề của bản backup trước incident

Giả sử:

~~~text
T0  Backup chứa wrappedDEK dưới KEK_v1 và IAM grants cũ
T1  Phát hiện compromise liên quan KEK_v1
T2  Production chuyển writers sang KEK_v2
T3  Rewrap/re-encrypt dữ liệu chính
T4  Restore bản backup tại T0
~~~

Nếu hệ thống tại T4 tự dùng lại grants, alias hoặc truststore cũ, key bị thu hồi có thể được tin trở lại. Mặt khác, nếu **KEK_v1 đã bị destroy** nhưng backup vẫn cần nó để mở dữ liệu hợp lệ, restore có thể thất bại.

Do đó cần **reconciliation sau restore**:

1. Đối soát **revocation epoch, key state, IAM grants** với nguồn có thẩm quyền hiện hành.
2. Kiểm tra key versions cần để đọc **encrypted data keys** trong snapshot.
3. Tách **read-only recovery environment** khỏi production traffic theo policy khi cần.
4. Nếu buộc phải truy cập key cũ để migrate dữ liệu, dùng quyền hẹp/approval/audit.
5. Không mở service trước khi xác minh **revoked signer, old MAC keys và trust anchors** không được dùng trái chính sách.

### 17.2. Retention và legal hold

Khi sự cố có yêu cầu điều tra, dữ liệu chứng cứ có thể cần được giữ theo **legal hold/retention**. Nhưng điều này khác với việc giữ **raw private key hoặc MAC secret** vô thời hạn ở kho không bảo vệ.

Nếu bằng chứng bắt buộc chứa key material, phải áp dụng **forensic secure storage, access control, logging, encryption và quy trình hủy khi hết nghĩa vụ**. Không suy từ việc có legal hold rằng mọi nhân viên IR đều được đọc mọi secret.

### 17.3. Chữ ký lịch sử và crypto agility

Hủy private signing key không cản trở **kiểm tra toán học chữ ký cũ** bằng public key, nếu message, signature và thuật toán còn sẵn. Tuy nhiên, việc đánh giá **độ tin cậy lịch sử** phụ thuộc issuer, certificate chain, status thu hồi, timestamp đáng tin và policy.

Với hồ sơ lưu lâu dài, có thể cần migration định dạng, thuật toán kiểm chứng và evidence preservation phù hợp. **Không ký lại âm thầm một chứng từ cũ bằng key mới** rồi coi đó là cùng một sự kiện pháp lý.

### 17.4. Crypto-erasure có giới hạn

Hủy DEK/KEK có thể khiến dữ liệu không còn giải mã được trong **phạm vi material và bản sao tổ chức quản lý**, nếu không còn đường khôi phục khác. Nhưng không thể thu hồi **raw key, ciphertext hoặc plaintext** mà attacker đã sao chép trước đó.

Vì vậy, forensic closing statement phải nêu: **key-v1 đã bị ngừng sử dụng ở những backend nào, những bản copy nào đã được chứng minh xử lý, và những copy ngoài kiểm soát nào có thể còn tồn tại**.

## 18. Case study: điều tra nghi lộ khóa tại hệ thống thanh toán đa tenant

Giả sử một nền tảng Java có:

- **Billing API** mã hóa hóa đơn tenant A/B bằng AES-GCM DEKs.
- **KMS KEK-prod-v3** bảo vệ wrapped DEKs, IAM được cấp theo workload.
- **Analytics Service** được phép xem dữ liệu tổng hợp, không được đọc raw PII.
- **Receipt Signing Service** ký biên nhận bằng Ed25519 private key non-exportable trong HSM.
- **JWKS/PKI** phân phối public signing keys cho bên xác minh.
- **SRE/Security/Data owner** quản lý incident, backups, migration và DR.

### 18.1. Phát hiện

Ở một khoảng thời gian không phù hợp, KMS ghi **Unwrap success** từ principal Analytics với context liên quan tenant A. Một SIEM alert đồng thời cho thấy Analytics container đã gọi một object store không nằm trong luồng bình thường.

**Điều đã biết:** Có operation KMS thành công và egress bất thường theo hai nguồn. **Điều chưa biết:** Raw KEK có lộ không? Plaintext DEK đã được lưu/đưa ra ngoài chưa? Luồng dữ liệu có liên quan đến cùng record không?

### 18.2. Containment

IR commander thu hồi Analytics principal, chặn những đường dữ liệu đang bị lạm dụng, giữ KMS/IAM và object-store event references. Đội không yêu cầu export KEK để “thử mở hóa đơn” và không destroy KEK-prod-v3 ngay.

### 18.3. Thu evidence

| Evidence ID | Nguồn | Phát hiện | Khoảng trống |
| --- | --- | --- | --- |
| EV-001 | KMS audit | Unwrap success theo keyId và principal | Không biết attacker có giữ plaintext DEK không |
| EV-002 | IAM policy history | Grant Unwrap mới được cấp trước alert | Ai là người thật dùng role cần xác minh |
| EV-003 | Billing data access metadata | Một số record references được truy vấn | Không chứa plaintext; có log sampling |
| EV-004 | Network egress | Lưu lượng bất thường tới endpoint ngoài dự kiến | Chưa xác minh loại nội dung được truyền |
| EV-005 | Secret/log scanner | Không thấy raw KEK trong logs đã kiểm | Chưa có coverage mọi dumps/backups |
| EV-006 | KMS policy after containment | Grant cũ đã bị revoke | Cần negative test và multi-region readback |

Những record này **là ví dụ giả định**, không phải kết quả forensic thực tế. Chúng phải được lưu cùng integrity/collection metadata theo quy trình.

### 18.4. Tái dựng khả năng ảnh hưởng

1. Từ EV-001 xác định các **KMS operations và request IDs thành công**.
2. Đối chiếu với EV-003 để tìm **records/tenants mà Analytics có thể đã đọc**.
3. Đối chiếu EV-004 nhằm đánh giá đường egress, không tự xem traffic là plaintext.
4. Tra inventory KEK→wrapped DEK→ciphertext để tính **potentially impacted set**.
5. Phân biệt **observed records** từ EV-003 với **additional records principal có thể truy cập** theo IAM/data permissions.
6. Không kết luận raw KEK bị lộ chỉ vì KMS Unwrap success; kiểm tra provider capability/export history.
7. Lập timeline từ trước grant lạ đến thời điểm revoke thực sự có hiệu lực, ghi log gaps.

### 18.5. Khắc phục

- Sửa **least-privilege grants** và business-level tenant/record authorization.
- Điều tra những DEKs đã có thể được trả ra; cân nhắc **DEK replacement/payload re-encryption** theo data risk.
- Nếu không có chứng cứ lộ raw KEK, vẫn có thể rotate KEK theo risk policy, nhưng không báo nó là “confirmed raw KEK exposure”.
- Kiểm tra Analytics service không còn dùng secret/cache cũ, và hệ thống hợp lệ vẫn đọc được dữ liệu thuộc quyền.
- Đối soát backup/DR và mọi region trước khi retire/destroy key material.

### 18.6. Kết luận có trách nhiệm

Một cách viết:

> Đã xác nhận các thao tác KMS Unwrap thành công bằng principal Analytics ngoài luồng được phê duyệt và đã thu hồi quyền API. Có một tập record references được quan sát và một tập dữ liệu tiềm năng rộng hơn theo grant. Chưa có đủ chứng cứ để khẳng định raw KEK đã bị xuất hoặc xác định toàn bộ plaintext đã bị exfiltrate. Dữ liệu còn cần được đánh giá để re-encrypt, và residual risk được theo dõi trong incident.

Đây là **kết luận ràng buộc bởi evidence**, không đánh đồng **không thấy bản sao raw KEK** với **chứng minh chắc chắn không hề có compromise**.

## 19. Ma trận kiểm thử tính đầy đủ của điều tra và khắc phục

Forensics thành công cần kiểm tra **evidence quality** và **remediation effectiveness**. Một phép Rotate thành công hoặc một phép decrypt(encrypt(x)) = x **không đủ**.

### 19.1. Kiểm tra evidence và timeline

| Test case | Kết quả mong đợi |
| --- | --- |
| Evidence artifact bị đổi một byte | SHA-256 khác bản gốc và có cảnh báo integrity |
| Chỉ có hash nhưng không có collector/source | Chưa được coi là chứng minh provenance |
| Hai log có cùng event ID ở hai accounts khác nhau | Không dedupe sai nếu ID chỉ unique trong account |
| KMS log đến muộn so với application trace | Timeline dùng event time + ingestion metadata |
| Host clock lệch 5 phút | Báo clock uncertainty, không diễn giải thứ tự sai chắc chắn |
| Log retention thiếu 48 giờ đầu | Báo gap thay vì “không có hoạt động” |
| Sign success nhưng không có raw-key export event | Kết luận API Sign abuse, không tự kết luận raw key leak |
| Plaintext DEK có mặt trong protected dump | Đánh giá boundary và quyền truy cập dump; không tự xác nhận attacker đọc |
| Public JWKS bị thay | Điều tra trust source, issuer, clients và cache |
| Chỉ có một application log do workload bị chiếm ghi | Cần corroboration từ nguồn độc lập |
| Secret được đính vào evidence ticket | Security control phát hiện, hạn chế truy cập và remediation |
| Working copy đã redacted | Có liên kết với original, method và access record |

### 19.2. Kiểm tra key state và dữ liệu sau sự cố

| Test case | Kết quả mong đợi |
| --- | --- |
| Principal đã bị revoke yêu cầu Unwrap | KMS/IAM từ chối, không có plaintext DEK trả về |
| Principal không có quyền yêu cầu Sign | HSM/KMS từ chối, audit ghi operation |
| Key v1 bị compromised vẫn được writer dùng Encrypt mới | Bị policy gate chặn và cảnh báo |
| Rewrap KEK-v1 sang KEK-v2 | Wrapped DEK metadata đúng; không báo DEK đã thay |
| Raw DEK-v1 đã lộ và dữ liệu cần bảo vệ tiếp | Đánh giá re-encrypt bằng DEK-v2, nonce mới, AEAD đúng |
| Migrate ciphertext với AAD sai | Decrypt thất bại, không tạo plaintext fallback |
| Migration race với writer | CAS/transaction ngăn ghi không nhất quán |
| JWT ký bằng signer revoked | Verifier áp dụng issuer/trust revocation policy, không chỉ Verify chữ ký |
| Relying party offline chưa cập nhật key | Được đánh dấu unacknowledged và residual risk |
| HMAC key v1 đã lộ trong planned overlap | Emergency cutover chặn chấp nhận v1 theo policy |
| Restore backup trước revoke | Reconcile IAM/grants/trust và không hồi sinh signer cũ |
| KEK còn phụ thuộc backup trước destroy | Pre-destruction review chặn hủy |
| KMS outage giữa remediation | Fail closed; không dùng raw KEK/hardcoded fallback |
| Old key bị disable trên một region | Kiểm tra region khác, không báo containment toàn cục |

### 19.3. Kiểm tra sự khác biệt giữa phép toán và hậu quả

Một test **KMS Unwrap success** có thể xác định backend trả plaintext DEK cho caller theo API contract. Nó **không tự chứng minh** caller đã ghi DEK ra file hoặc có người ngoài đọc được.

Một test **signature Verify=true** không chứng minh tài liệu đã được business owner phê duyệt. Một test **JWKS v2 fetch thành công** không chứng minh tất cả clients đều đã quên v1. Cần test **authorization, acceptance, data access và cache/revocation propagation** ở đúng tầng.

## 20. Anti-pattern: lỗi pháp chứng làm trầm trọng thêm sự cố

| Sai lầm | Vì sao sai | Thay bằng |
| --- | --- | --- |
| **Ghi raw DEK/private key vào incident ticket** | Tạo bản sao bí mật ngoài boundary, tăng người truy cập | Key reference, artifact ID, protected forensic vault |
| **Dump toàn bộ RAM lên nơi chia sẻ công khai** | Mang cả tokens, secrets, PII ra ngoài | Phương pháp thu được phê duyệt, scope tối thiểu, encrypted custody |
| **Gọi ExportKey để kiểm tra key có lộ không** | Tự tạo đường lộ key mới | Metadata/provenance/policy evidence và negative tests có kiểm soát |
| **Dùng KMS Decrypt trên dữ liệu sản xuất để “test” hàng loạt** | Sinh plaintext và audit noise không cần thiết | Authorized sample/readback và evidence review |
| **Xóa logs ngay vì trong đó có secret** | Có thể hủy bằng chứng và mất timeline | Hạn chế truy cập, giữ chứng cứ theo policy rồi remediation |
| **Giữ workload độc hại chạy vô hạn để bắt log** | Tiếp tục gây rò hoặc ký giả | IR cân bằng preservation với containment, giới hạn thời gian |
| **Hash một artifact rồi khẳng định nó chính chủ** | Hash không có source authentication độc lập | Provenance, custody, trusted collection/signature |
| **Báo “không exfiltration” vì egress nhỏ** | Raw DEK có thể chỉ vài chục byte | Phân tích capability, các đường dữ liệu và log gaps |
| **Báo raw KEK leak từ một Unwrap success** | API misuse không chứng minh material đã export | Phân biệt output DEK, raw KEK và grant abuse |
| **Dùng alias hiện tại để suy ra key quá khứ** | Alias mutable, key version có thể khác | Lịch sử key mapping/material version |
| **Tin tenantId của request trong audit** | Client có thể giả trường tenant | Ownership/authorization từ nguồn độc lập |
| **Coi mọi signature Verify=true là hợp pháp** | Chữ ký không kiểm tra business semantics/trust status | Issuer/purpose/claims/revocation và authorization |
| **Mở rộng kết luận từ một vùng sang mọi region** | Replication, logging và grants khác nhau | Scope coverage theo account/region/provider |
| **Trộn event time với ingestion time** | Timeline sai thứ tự | UTC, clock skew, độ trễ, source timestamp metadata |
| **Dedupe theo tên key thay vì key ID/version** | Trộn nhiều materials hoặc tenants | Stable identifiers + key inventory |
| **Rewrap rồi báo raw DEK đã được thay** | DEK vẫn giống nhau | Re-encrypt dữ liệu khi raw DEK bị lộ |
| **Destroy KEK trước khi kiểm backup** | Mất khả năng phục hồi ciphertext cũ | Dependency/retention/DR checks |
| **Thu hồi KMS grants rồi bỏ qua bản secret đã export** | Raw key còn tồn tại ngoài control plane | Rotation, data/trust impact và residual risk |
| **Chỉ nhìn dashboard “resolved”** | Không chứng minh key usage/trust đã chuyển | Readback, negative tests, consumer ack và telemetry |
| **Không lưu uncertainty và alternative hypotheses** | Báo cáo trông chắc chắn nhưng không được hỗ trợ | Confidence, gaps và peer-reviewed conclusions |
| **Sao chép log nhạy cảm vào nhiều tools bên ngoài** | Mở rộng phạm vi xử lý dữ liệu trái policy | Forensic workbench được phê duyệt, access audit |

## 21. Mẫu báo cáo forensic sau compromise

Một báo cáo ngắn có thể dùng cấu trúc sau, với mọi phần được gắn **evidence IDs** và mức chắc chắn phù hợp.

~~~text
CASE ID:
KEYS / KEY VERSIONS / PURPOSES:
OWNER / ENVIRONMENT / TENANT SCOPE:

1. Executive finding
   - Confirmed facts:
   - Probable / possible impacts:
   - Unknown and evidence gaps:

2. Incident timeline
   - Earliest observed suspicious event:
   - First known unauthorized operation:
   - Detection time:
   - Containment effective time:
   - Rotation / re-encryption / trust update times:

3. Evidence register
   - Evidence IDs, sources, collector, UTC collection time:
   - Integrity hashes and custody:
   - Known gaps / retention / sampling / clock skew:

4. Key and asset dependency map
   - Key/KEK/DEK versions and provider behavior:
   - Ciphertexts, signatures, public verifiers, partners:
   - Backups/DR and old versions:

5. Technical analysis
   - Raw material exposure vs key API abuse vs trust tampering:
   - Observed activity vs theoretical capability:
   - Alternative explanations and confidence:

6. Containment and remediation evidence
   - Revocation/IAM/KMS state:
   - Key replacement and migration:
   - Consumer trust updates:
   - Negative tests, readback, restore tests:

7. Residual risk
   - Data/key copies outside control:
   - Partners/regions without acknowledgements:
   - Evidence limitations and follow-up:

8. Decisions and approvals
   - Incident commander / key owner / data owner / approvers:
   - Closure criteria, policy versions, audit references:
~~~

### 21.1. Phân biệt phạm vi observed và potential

Ví dụ cách diễn đạt:

> **Observed:** 12 record references có KMS Unwrap thành công được liên kết bằng provider event IDs. **Potential:** Principal có quyền truy cập thêm tới các records của tenant A theo grant và application role trong cửa sổ T1–T2. **Not established:** Chưa có chứng cứ đầy đủ cho việc raw KEK đã bị xuất hoặc toàn bộ plaintext đã được exfiltrate.

Một báo cáo như vậy hữu ích hơn câu “đã mất 12 records” nếu điều kiện thực sự mới chỉ chứng minh 12 **Unwrap operations**. Cần phân biệt key operation, business data access và bên nhận cuối.

### 21.2. Kết luận phải có scope và thời gian

Không viết “không có malicious signing activity” nếu chỉ xem logs của một HSM region trong một giờ. Viết **“không phát hiện trong các audit sources đã kiểm, từ T1 tới T2, tại region X”**, rồi ghi rõ phạm vi còn thiếu.

Không xem **root cause corrected** đồng nghĩa **historical exposure remediated**. Key replacement giúp hạn chế tác hại tương lai; dữ liệu/chữ ký đã mất kiểm soát có thể vẫn cần xử lý nghiệp vụ hoặc thông báo theo chính sách và luật áp dụng.

## 22. Checklist forensic sau compromise

Trước khi kết thúc điều tra, hãy kiểm tra:

1. **Case ownership:** Có incident commander, key owner, data owner, IR và người phê duyệt?
2. **Key identity:** Đã xác định đúng key ID, material version, alias history, algorithm, purpose?
3. **Classification:** Đã tách raw key exposure, API misuse, IAM abuse, trust substitution và crypto misuse?
4. **Confidence:** Mỗi kết luận có confirmed/probable/possible/unknown và evidence reference?
5. **Timeline:** Có UTC time, ingestion time, collection time, clock skew và gaps?
6. **Chain of custody:** Có collector, acquisition method, artifact hash, transfer/access records?
7. **Original preservation:** Bản gốc được bảo vệ; phân tích dùng working copies được quản lý?
8. **Secret minimization:** Không đưa raw keys/tokens/PII vào ticket, report hoặc log mới?
9. **KMS coverage:** Đã xem đủ operation types, key versions, accounts/regions và audit retention?
10. **IAM history:** Có grants/policy/session state trước, trong và sau incident?
11. **Application correlation:** KMS event gắn với verified record/tenant/principal ở đâu?
12. **DEK/KEK graph:** Đã liệt kê wrapped DEKs, ciphertext và key dependencies?
13. **Signing scope:** Có public key consumers, signed objects, token sessions và trusted timestamps khi cần?
14. **HMAC scope:** Biết các bên giữ shared secret và anti-replay state?
15. **Trust source:** Đã kiểm JWKS/PKI/truststore changes, certificate status và cache?
16. **RNG/nonce:** Có kiểm tra entropy/nonce reuse nếu dấu hiệu hướng tới lỗi primitive?
17. **Observed versus potential:** Đã tách hoạt động quan sát được khỏi khả năng truy cập?
18. **Exfiltration uncertainty:** Có nêu network/storage coverage và giới hạn kết luận?
19. **Alternate explanations:** Đã kiểm rotation job, backup, migration hoặc hoạt động hợp lệ?
20. **Containment:** Có evidence principal/grant/operation nguy hiểm đã bị chặn?
21. **Key replacement:** Vật liệu mới được tạo từ ranh giới tin cậy, đúng purpose/algorithm?
22. **Data remediation:** Khi raw DEK lộ, đã đánh giá re-encrypt thay vì chỉ rewrap?
23. **Record integrity:** Migration kiểm tra AEAD tag/AAD, version và concurrency?
24. **Public trust propagation:** Clients/verifiers/partners đã cập nhật hoặc có residual risk?
25. **Old-key use:** Có kiểm tra old Sign/Encrypt/Wrap sau cutover?
26. **Backup/DR:** Restore không hồi sinh revoked grants/trust và vẫn khôi phục được dữ liệu hợp lệ?
27. **Legal hold/retention:** Quy trình evidence và key destruction có được phê duyệt?
28. **Negative tests:** Có test KMS AccessDenied, wrong tenant, wrong AAD, revoked key và cache cũ?
29. **Root cause:** Đã sửa lỗ hổng IAM, logging, CI, trust distribution hoặc nonce allocator?
30. **Final report:** Có evidence register, timeline, scope, confidence và root-cause analysis?
31. **Residual risk:** Những key/data copies đã mất kiểm soát và unknown được ghi rõ?
32. **Review/closure:** Owners phê duyệt, có follow-ups và giới hạn lời khẳng định?

## 23. Ghi nhớ

- **Forensics sau compromise là điều tra bằng chứng**, không chỉ là thao tác thay hoặc thu hồi khóa.
- Phải **phân biệt raw key material bị lộ, KMS/HSM API bị lạm dụng, credential compromise và public-trust substitution**; chúng có đường tấn công, mức chứng cứ và remediation khác nhau.
- **Evidence cần provenance, integrity, chain of custody, UTC timeline và giới hạn truy cập.** Hash giúp phát hiện thay đổi, nhưng không tự chứng minh nguồn gốc hoặc sự thật của log.
- **Không thu thập raw secrets nếu metadata đủ**; một heap dump, audit export hay ticket chứa plaintext DEK có thể trở thành sự cố rò dữ liệu mới.
- **KMS Unwrap/Sign success chỉ chứng minh operation trong phạm vi log**, không tự xác nhận raw KEK/private key đã rời HSM hay plaintext đã bị exfiltrate.
- **DEK/KEK compromise phải được phân tích qua dependency graph**: KEK → wrapped DEKs → ciphertext → tenant/backup. Rewrap không sửa việc raw DEK đã bị lộ.
- **Chữ ký đúng toán học không đủ để tin giao dịch**, đặc biệt khi private signer hoặc JWKS trust bị compromise. Cần issuer/purpose/authorization và chứng cứ thời gian phù hợp.
- **Timeline cần phân biệt event, ingestion, collection và effective times**. Thiếu log không phải chứng cứ không có hành vi tấn công.
- **Containment, key replacement, data remediation, trust propagation và recovery validation là các mốc khác nhau**; không gom tất cả vào status “ROTATED”.
- **Backup/DR có thể giữ ciphertext hoặc IAM/trust cũ**. Restore phải đối soát với revocation policy hiện hành, đồng thời destruction không được làm mất dữ liệu còn cần.
- **Báo cáo phải tách confirmed, probable, possible, unknown và residual risk**, với mỗi khẳng định được hỗ trợ bằng evidence references.

Khi điều tra **Forensics sau compromise**, hãy đặt ba câu hỏi: **“Chúng ta thực sự quan sát được điều gì và bằng chứng có đáng tin không?”, “Khóa, quyền sử dụng và dữ liệu nào có thể đã bị ảnh hưởng ngoài phần đã nhìn thấy?”, “Có thể chứng minh containment, recovery và giới hạn rủi ro tồn dư bằng những kiểm thử và hồ sơ nào?”** Chỉ khi trả lời được bằng **key inventory, KMS/HSM audit, IAM, chain of custody, timeline, dữ liệu phụ thuộc và xác minh độc lập**, tổ chức mới có thể xử lý sự cố khóa mật mã với kết luận đáng tin cậy mà không tạo thêm rủi ro.
