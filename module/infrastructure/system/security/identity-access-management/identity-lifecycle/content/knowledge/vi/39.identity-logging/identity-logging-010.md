# Log integrity trong Identity logging: bảo toàn và kiểm chứng bằng chứng truy cập IAM

**Log integrity** (*tính toàn vẹn của nhật ký*) là khả năng bảo đảm hoặc **phát hiện một cách đáng tin cậy** khi nội dung, thứ tự, quan hệ và metadata quan trọng của các bản ghi log bị thay đổi ngoài quy trình cho phép sau khi được ghi nhận. Trong **Identity and Access Management (IAM)**, log integrity giúp trả lời các câu hỏi kiểm toán sống còn: **ai yêu cầu và phê duyệt quyền? hệ thống nào đã cấp quyền? ai đăng nhập hay sử dụng đặc quyền? quyền bị thu hồi lúc nào? có ai xóa hoặc sửa dấu vết để che giấu hành vi không?**

Giả sử HRIS phát sự kiện Leaver cho Lan lúc 09:00, IAM ra lệnh disable tài khoản lúc 09:02, nhưng một admin cố xóa dòng `ACCOUNT_DISABLE_FAILED` khỏi nhật ký. Nếu log nằm trên máy mà admin đó có quyền chỉnh sửa, báo cáo “đã offboard thành công” có thể sai mà khó phát hiện. Thiết kế tốt sẽ **thu thập sự kiện từ nguồn đáng tin, truyền qua kênh bảo vệ, lưu theo cơ chế giới hạn sửa/xóa, liên kết bản ghi bằng hash/signature khi phù hợp, kiểm soát khóa và kiểm tra sự thiếu hụt sự kiện**. Khi có sai lệch, bộ phận Security phải có đủ bằng chứng để xác định **phạm vi không còn tin cậy** và xử lý quyền tồn dư.

Bài thuộc chương **Identity logging** của module **Security — Identity and Access Management (IAM) — Identity Lifecycle**. Phạm vi module là mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo account/cấp quyền đến rà soát, thay đổi vai trò và thu hồi; có liên hệ **IdP, SSO, SCIM, RBAC/ABAC, PAM, service/machine identities, audit và deprovisioning**. Bài tập trung vào **độ tin cậy của dấu vết**, không chỉ cách bật tính năng ghi log.

> **Nguyên tắc:** “Log có SHA-256” **không đồng nghĩa log chống sửa đổi**. Nếu kẻ tấn công có thể sửa nội dung **và tính lại hash**, hoặc có thể xóa cả log lẫn bảng hash, kiểm tra hash vẫn có thể báo hợp lệ. Tính toàn vẹn cần **trust boundary, ràng buộc chuỗi hoặc bằng chứng bất đối xứng, anchor/checkpoint ngoài tầm kiểm soát của người ghi, quyền lưu trữ hạn chế và verification độc lập**.

## 1. Log integrity bảo vệ điều gì?

Trong một hệ thống IAM, log có thể là **bằng chứng thực hiện kiểm soát** chứ không chỉ thông tin debug. Một event về người được cấp `ProductionAdmin` giúp kiểm toán so quyết định cấp quyền, phê duyệt, hành động của connector và quyền hiệu lực ở ứng dụng đích.

**Tính toàn vẹn** nhằm cho phép tin rằng **bản ghi được dùng làm bằng chứng** là bản ghi thực sự đã được tạo/tiếp nhận trong điều kiện được định nghĩa và không bị thay đổi trái phép sau đó. Nó bao gồm:

1. **Content integrity** — trường quan trọng không bị sửa: actor, target, action, result, policy, timestamp.
2. **Ordering integrity** — thứ tự trong phạm vi một nguồn/partition có thể được kiểm tra; không bị lặng lẽ đảo.
3. **Append integrity** — khó hoặc có thể phát hiện chèn bản ghi giả, thay record cũ bằng record khác.
4. **Deletion/truncation detection** — phát hiện mất dòng, mất một đoạn hoặc mất suffix log khi có sequence/checkpoint.
5. **Origin authenticity** — biết record do nguồn/agent được tin phát ra, nếu có chữ ký/MAC và cơ chế định danh nguồn.
6. **Evidence provenance** — theo dõi nguồn, lúc thu thập, transformations, phiên bản schema, nơi lưu và ai đã truy cập.
7. **Tamper detection** — có quy trình kiểm chứng tính toàn vẹn định kỳ và khi có sự cố.

Các đặc tính trên **không tự động có chỉ vì tên tính năng “audit logging”**. Cần thiết kế từng lớp.

### 1.1. Integrity khác các thuộc tính bảo mật khác

| Thuộc tính | Câu hỏi | Ví dụ trong IAM |
| --- | --- | --- |
| **Integrity** | Log có bị sửa/xóa/chèn ngoài quy trình không? | Dòng `PAM_SESSION_STARTED` còn nguyên. |
| **Authenticity** | Nguồn phát sự kiện có đúng là thành phần được tin không? | Event thực sự từ IdP production, không phải service giả. |
| **Completeness** | Mọi sự kiện cần ghi có được tạo và thu thập không? | Không mất event `ROLE_REVOKED` trong outage. |
| **Confidentiality** | Ai được đọc dữ liệu trong log? | Không lộ email, device/IP, credential hoặc nội dung nhạy cảm. |
| **Availability** | Log có thể truy xuất khi cần điều tra/kiểm toán không? | Security xem audit khi cluster ứng dụng bị lỗi. |
| **Durability** | Log đã nhận có còn được lưu theo retention? | Không mất sau crash hoặc disk failure. |
| **Correctness/semantic validity** | Nội dung event phản ánh đúng sự thật nghiệp vụ không? | `REVOKED` chỉ được dùng khi quyền thực tế đã mất. |
| **Non-repudiation** | Mức độ bằng chứng khiến một chủ thể khó phủ nhận hành động? | Phụ thuộc identity binding, key custody và trust, không tự xuất hiện từ hash. |

**Integrity không chứng minh correctness hoặc completeness.** Một hệ thống có thể ký một log sai từ đầu hoặc cố tình **không tạo event**. Một chuỗi hash “valid” trên dữ liệu thiếu vẫn có thể là dữ liệu thiếu.

### 1.2. Mục tiêu phải diễn đạt theo threat model

Không có nghĩa “kẻ nào cũng không thể sửa log”. Nên hỏi:
- Chống **developer/operator** vô tình sửa file?
- Chống **local admin** trên server bị xâm nhập?
- Chống **service account** bị đánh cắp có quyền ghi storage?
- Chống **cloud storage administrator** xóa/chỉnh object?
- Chống người có quyền **tạo log và sửa retention**?
- Chống insider có khả năng thay đổi cấu hình SIEM?
- Có cần bằng chứng sử dụng với kiểm toán độc lập hoặc pháp lý không?

Từng attacker có khả năng khác nhau; thiết kế cần nêu **ai được tin, ai không và giới hạn của bằng chứng**.

## 2. IAM cần log những sự kiện nào để kiểm chứng vòng đời danh tính?

Một hệ thống Identity Lifecycle có nhiều nguồn sự kiện:

| Giai đoạn/chức năng | Sự kiện đáng ghi | Vì sao toàn vẹn quan trọng? |
| --- | --- | --- |
| **Identity proofing** | Xác minh nhân sự/nhà thầu, nguồn authoritative, kết quả. | Ngăn che giấu việc tạo identity không được xác minh. |
| **Joiner provisioning** | Account created, baseline role granted, MFA enrollment. | Chứng minh tài khoản/quyền ban đầu hợp lệ. |
| **Mover** | HR assignment changed, old grant removed, new role approved. | Phát hiện tích lũy quyền cũ khi đổi vai trò. |
| **Leaver** | HR termination event, disable issued, target readback verified. | Không che giấu account còn hoạt động sau offboarding. |
| **IdP/SSO** | Successful/failed login, MFA challenge, session created/revoked. | Truy vết đăng nhập bất thường. |
| **OAuth/OIDC** | Token issued, client auth failed, client secret rotated, revoked grant. | Phát hiện app-only token hoặc credential bị lạm dụng. |
| **SCIM** | Create/PATCH/DELETE, target response, reconciliation result. | Không tráo trạng thái provisioning khi connector lỗi. |
| **RBAC/ABAC** | Role/group/policy change, authorization decision quan trọng. | Chứng minh ai sửa quyền, ảnh hưởng scope nào. |
| **PAM/JIT** | Eligibility, activation, session, checkout, revoke. | Ngăn xóa dấu vết đặc quyền khẩn cấp. |
| **Access review/SoD** | Reviewer decision, exception approval, compensating-control check. | Chứng minh phê duyệt độc lập và expiry hợp lệ. |
| **Machine/service identities** | Workload created/retired, key/cert rotation, grant changed. | Không bỏ sót quyền kỹ thuật tồn dư. |
| **Audit system** | Log policy changed, ingest disabled, retention altered, verification failed. | Phát hiện tấn công lên chính pipeline bằng chứng. |

### 2.1. Decision, execution và verification là các event khác nhau

~~~text
09:00  HR_LEAVER_CONFIRMED
09:01  IAM_DEPROVISION_TASK_CREATED
09:02  TARGET_DISABLE_REQUEST_SENT
09:02  TARGET_DISABLE_RESPONSE_RECEIVED
09:03  TARGET_ACCOUNT_READBACK
09:05  SESSION_TOKEN_REVOCATION_CHECKED
09:06  DEPROVISION_VERIFIED_CLOSED
~~~

Nếu chỉ ghi `DEPROVISION_VERIFIED_CLOSED`, không thể kiểm tra liệu kết luận đó có dựa trên target readback thật. Log integrity chỉ bảo vệ nội dung có ghi; **quy trình vẫn phải tạo đủ evidence đúng thời điểm**.

### 2.2. Chỉ ghi metadata phù hợp

Log không nên chứa password, OTP, refresh token, client secret, private key, session cookie, toàn bộ Authorization header hoặc tài liệu nhạy cảm. Với identities, thường chỉ cần **stable ID, target reference, action, outcome, approval/policy reference, correlation ID** và dữ liệu tối thiểu để điều tra.

## 3. Mô hình đe dọa đối với log IAM

| Mối đe dọa | Thao tác kẻ tấn công có thể làm | Bằng chứng/cơ chế cần có |
| --- | --- | --- |
| **Sửa nội dung** | Đổi `DENY` thành `PERMIT`. | Hash/MAC/signature + trusted canonicalization. |
| **Xóa một record** | Bỏ event privilege escalation. | Sequence, hash-chain hoặc gap detection, checkpoint. |
| **Cắt đuôi log** | Xóa mọi event sau 11:00. | External anchor, heartbeat, expected source continuity. |
| **Chèn record giả** | Thêm event approval không tồn tại. | Origin authentication và signature/MAC, policy controls. |
| **Đảo thứ tự** | Đặt approval trước grant dù thực tế sau. | Per-source sequence, timestamp metadata, causal correlation. |
| **Replay** | Gửi lại event cũ như mới. | Unique event ID, sequence, idempotency/deduplication. |
| **Thay thời gian** | Làm lệch quyết định khỏi deadline. | Trusted receive time + clock-skew checks và time sync. |
| **Sửa pipeline** | Tắt audit, đổi filter/drop rule. | Configuration audit riêng, independent monitoring. |
| **Sửa khóa** | Đổi HMAC key hoặc signing key để forge. | KMS/HSM, key governance, rotation, audit, anchored public keys. |
| **Storage deletion** | Xóa bucket/log objects. | Object immutability/retention, external copies và alarm. |
| **Suppress events** | Không gửi logs hoặc tắt agent. | Heartbeat, source inventory, sequence/gap/lag alerts. |
| **Compromise producer** | Phát event gian dối nhưng ký hợp lệ. | So sánh độc lập HRIS/target/IdP/PAM; không chỉ chữ ký. |

### 3.1. Threat model không chỉ là attacker xóa file

Một admin có thể không sửa object trong storage immutable, nhưng có thể:
- Vô hiệu hóa audit trước khi thao tác.
- Tạo policy filter bỏ sự kiện `ROLE_GRANTED`.
- Thay đổi clock của nguồn.
- Đưa dữ liệu sai từ chính producer.
- Dùng một account khác không có log capture.
- Làm log ingestion queue đầy và mất event.
- Thay audit query/report để che một bản ghi.

Vì vậy cần **end-to-end controls** từ event source tới evidence consumption, không chỉ bật WORM trên storage.

## 4. Pipeline log đáng tin: tạo, vận chuyển, lưu, kiểm chứng

~~~mermaid
flowchart LR
    HR["HRIS / JML"] --> A["Source event producers"]
    IDP["IdP / SSO / OAuth"] --> A
    SCIM["SCIM / target API"] --> A
    PAM["PAM / admin / PEP"] --> A
    A --> B["Trusted agent / collector"]
    B --> C["Authenticated transport + buffering"]
    C --> D["Central ingest / schema validation"]
    D --> E["Append / sequence / hash / signature"]
    E --> F["Immutable or versioned log archive"]
    E --> G["SIEM / detection / query copy"]
    F --> H["Independent verifier / checkpoint"]
    H --> I["Audit evidence / incident response"]
    G --> I
~~~

### 4.1. Không tin một máy nguồn đã bị chiếm

Khi attacker có quyền root trên app server, local log files **không phải nguồn bằng chứng duy nhất đáng tin**. Một chiến lược thông thường là:
- Phát sự kiện sớm sang collector/queue ngoài máy.
- Hạn chế khả năng app/process đọc hoặc sửa log đã chuyển.
- Dùng xác thực collector và TLS/mTLS.
- Giữ archive immutable hoặc các checkpoints độc lập.
- Theo dõi khoảng thời gian source dừng gửi.
- So khớp với logs từ **downstream target hoặc independent audit source**.

**Bảo vệ remote logging không chứng minh event không bị giả ngay tại producer**. Nó chỉ nâng khả năng bảo toàn những event mà collector đã nhận.

### 4.2. Raw log và enriched log

Nên phân biệt:
- **Raw source event**: sự kiện gốc/byte representation đã được thu nhận.
- **Normalized/enriched event**: thêm identity mapping, geo/risk fields, schema chuẩn hóa.
- **Analytical projection**: indexes, dashboards và reports.

Không nên **ghi đè raw evidence** mỗi lần enrichment logic thay đổi. Nên có `sourceEventRef`, `transformationVersion` và trace từ kết quả phân tích trở về event gốc.

### 4.3. SIEM không nhất thiết là evidence archive

SIEM có thể tối ưu truy vấn, phân tích và alert; retention/indexing/đặc quyền của nó có thể không đáp ứng yêu cầu **immutability**. Tùy kiến trúc, lưu **bản gốc hoặc hash/checkpoint trong archive tách biệt**, rồi dùng SIEM như một read/index layer.

## 5. Hash: thành phần nền tảng nhưng chưa đủ

Một cryptographic hash function như SHA-256 ánh xạ dữ liệu thành digest cố định.

~~~text
eventBytes = UTF8(canonicalEvent)
digest     = SHA-256(eventBytes)
~~~

Nếu nội dung đổi, digest gần như chắc chắn đổi khi dùng thuật toán băm mật mã phù hợp. Nhưng cần biết **digest ban đầu có được giữ độc lập và đáng tin** hay không.

### 5.1. Lỗi “hash và dữ liệu nằm cùng một nơi có thể sửa”

~~~text
events.log:
  {"action":"PAM_ACTIVATED","subject":"person-2048"}

events.sha256:
  0a12... (hash của events.log)
~~~

Nếu attacker có quyền sửa cả `events.log` lẫn `events.sha256`, họ có thể thay event và tính lại hash. Kiểm tra cặp file mới vẫn pass. Do đó một digest đơn lẻ **phát hiện hỏng dữ liệu ngẫu nhiên** tốt, nhưng không tự bảo vệ trước người kiểm soát **dữ liệu và bằng chứng hash**.

### 5.2. Checksum khác cryptographic hash

CRC/checksum dùng để phát hiện lỗi truyền/lưu trữ vô ý, **không phù hợp làm bằng chứng chống attacker chủ động**. Khi thiết kế tamper-evidence, dùng hash mật mã hiện đại và cơ chế chứng thực/anchor phù hợp; tránh thuật toán đã yếu trước collision cho mục đích này.

### 5.3. Canonicalization là điều kiện kiểm tra nhất quán

Hai JSON biểu diễn cùng ý nghĩa có thể có byte khác nhau vì thứ tự key, whitespace hoặc escaping:

~~~json
{"actor":"person-2048","action":"LOGIN"}
~~~

~~~json
{
  "action": "LOGIN",
  "actor": "person-2048"
}
~~~

Nếu ký/hash **raw bytes**, hai JSON trên khác digest; nếu muốn ký **semantic JSON**, cần một **quy tắc canonicalization được versioned** mà cả writer và verifier thực hiện như nhau, ví dụ chuẩn canonical JSON được chấp thuận. Không chỉ `JSON.stringify` tùy triển khai rồi giả định mọi ngôn ngữ, số dấu phẩy động và Unicode đều đồng nhất.

### 5.4. Tránh tự sửa event sau khi hash

Nếu pipeline thêm `geoCountry` sau lúc ký event mà lại ghi đè nội dung event gốc, signature có thể không hợp lệ. Hãy giữ **raw signed event** và thêm enrichment dưới dạng một **record dẫn chiếu** với version của transform.

## 6. HMAC: chứng minh dữ liệu biết một khóa bí mật chung

**HMAC-SHA-256** tạo message authentication code dựa trên key bí mật và nội dung event:

~~~text
tag_i = HMAC-SHA256(K, canonical(event_i))
~~~

Nếu attacker không có `K`, họ khó tạo tag hợp lệ cho dữ liệu bị sửa. Tuy nhiên HMAC là **symmetric authentication**:
- Writer và verifier nắm cùng key hoặc cùng khả năng gọi MAC service.
- Một bên có key có thể **tạo tag mới cho record giả**.
- Bằng chứng “do đúng một người ký” hoặc non-repudiation độc lập **không đạt** chỉ nhờ HMAC.
- Key bị lộ thì tính tin cậy của các records trong phạm vi key cần được đánh giá lại.

### 6.1. Kiểm soát HMAC key

- Sinh key bằng nguồn ngẫu nhiên mật mã.
- Lưu qua KMS/HSM hoặc secret manager theo policy.
- Giới hạn principal có quyền **generate MAC** khác với principal chỉ **verify** khi kiến trúc cho phép.
- Chỉ định `keyId`/version trong metadata record.
- Rotate key theo chu kỳ hoặc khi compromise.
- Giữ khả năng verify bằng key cũ trong retention nhưng **không cho ký mới** trái policy.
- Audit mọi lần cấp/quyền sử dụng key.

### 6.2. HMAC không tự phát hiện missing events

Nếu chỉ gửi 99/100 sự kiện, 99 tags đều hợp lệ. Cần **sequence, checkpoints, heartbeats và independent reconciliation** để đánh giá completeness.

## 7. Chữ ký số cho log: ai có quyền ký và ai có quyền kiểm?

Với **digital signature**, một thành phần đáng tin giữ **private signing key**; nhiều auditor/verifier có thể dùng **public key** để kiểm chứng records hoặc batch digest.

~~~text
signature_i = Sign(privateKey, digest_i)
verified    = Verify(publicKey, digest_i, signature_i)
~~~

Điểm mạnh so với shared HMAC là verifier không cần khả năng tạo chữ ký mới. Nhưng vẫn phải xác định:
- Public key thực sự thuộc nguồn/chức năng nào?
- Private key được bảo vệ và cấp quyền ký cho ai?
- Chữ ký gắn với event nào, schema/version, timestamp, sequence và source nào?
- Signing service có thể bị lạm dụng để ký event giả không?
- Key compromise hoặc rotation được kiểm toán ra sao?

### 7.1. Chữ ký của collector khác chữ ký nguồn

**Producer-signed log** có thể giúp chứng minh event gắn với nguồn đã sở hữu private key. Nhưng khi producer bị chiếm, attacker có thể gửi log gian dối đã ký.

**Collector-signed receipt/checkpoint** giúp chứng minh collector đã **nhận** event tại một thời điểm theo chính sách. Nó không tự chứng minh event do producer mô tả là sự thật.

Thiết kế đáng tin thường kết hợp **source identity, collector receipt, independent target-side evidence và tamper-evident archive**.

### 7.2. Chữ ký không bảo vệ bí mật nội dung

Hash/MAC/signature chứng minh integrity/authenticity trong giới hạn, **không mã hóa log**. Nếu log chứa PII hoặc security-sensitive metadata, vẫn cần encryption/access controls và data minimization.

## 8. Hash chain: liên kết thứ tự và phát hiện sửa record giữa chuỗi

Một **hash chain** gắn digest của bản ghi trước vào bản ghi kế tiếp:

~~~text
H_0 = trustedGenesisOrCheckpoint

H_i = SHA-256(
    encode(H_(i-1)) ||
    encode(sequence_i) ||
    encode(length(canonicalEvent_i)) ||
    canonicalEvent_i
)
~~~

**`||` nghĩa là nối dữ liệu có framing rõ ràng**, không phải ghép chuỗi tùy ý để có thể gây ambiguity. Cần chuẩn hóa encoding, byte length, domain separation và version.

### 8.1. Ví dụ ba sự kiện

~~~text
event #101: ACCESS_REQUEST_APPROVED
    H101 = Hash(H100, 101, canonical(event101))

event #102: GROUP_MEMBERSHIP_ADDED
    H102 = Hash(H101, 102, canonical(event102))

event #103: TARGET_GRANT_READBACK_VERIFIED
    H103 = Hash(H102, 103, canonical(event103))
~~~

Nếu event #102 bị sửa hoặc xóa mà không tính lại phần sau, verifier phát hiện chuỗi bị đứt. Nếu attacker có thể **viết lại toàn bộ suffix và thay checkpoint cuối**, một hash chain **chưa có anchor độc lập** vẫn có thể bị làm giả.

### 8.2. Genesis và external anchor

Cần lưu/bảo vệ:
- Genesis hash hoặc start checkpoint.
- Stream ID, sequence range, prior checkpoint.
- Batch ending hash/sequence.
- Signing/MAC key metadata.
- External checkpoint ở boundary mà writer không thể sửa: archive độc lập, trusted signer hoặc log ledger/monitoring service được phân quyền.

**Anchor làm tăng khả năng phát hiện sửa dữ liệu lịch sử** sau thời điểm anchor được bảo vệ. Nó không tự chứng minh mọi event đáng lẽ phải tồn tại đã được tạo.

### 8.3. Một stream khác nhiều stream đồng thời

Một hệ thống gồm hàng trăm producers khó tạo **một thứ tự tuyệt đối** nếu không có sequencer đáng tin. Có thể dùng:
- **Per-source hoặc per-partition sequence/hash chain**.
- Ingest receipt sequence tại collector.
- Batch/checkpoint cho từng nguồn/partition.
- Correlation IDs và causal links để so giao dịch xuyên nguồn.
- Signed digest/anchor của mỗi stream theo lịch.

Không suy từ hai timestamps khác nhau rằng toàn hệ thống có **total order chắc chắn** khi network latency và clock skew tồn tại.

## 9. Merkle tree và batch integrity cho log quy mô lớn

Khi hàng triệu events được ghi mỗi ngày, có thể băm events thành các lá và xây **Merkle tree**:

~~~text
leaf_1 = H(domain_leaf || event_1)
leaf_2 = H(domain_leaf || event_2)
leaf_3 = H(domain_leaf || event_3)
leaf_4 = H(domain_leaf || event_4)

parent_12 = H(domain_node || leaf_1 || leaf_2)
parent_34 = H(domain_node || leaf_3 || leaf_4)
root      = H(domain_node || parent_12 || parent_34)
~~~

Root có thể được **ký và anchor độc lập**. Một **Merkle inclusion proof** cho phép kiểm tra event thuộc batch mà không cần gửi toàn bộ batch, nếu tree construction và root đáng tin.

### 9.1. Inclusion khác completeness

Một proof cho event #58 chứng minh nó thuộc batch đã cam kết; **không chứng minh event #57 hay #59 đáng lẽ phải tồn tại và đã có**. Có thể cần:
- Batch manifest và record count.
- Sequence range/gap detector.
- Checkpoints liên tiếp.
- Proof/monitor cho append-only consistency nếu dùng transparency log.
- Reconciliation với target events.

### 9.2. Merkle không thay tất cả các control

Merkle phù hợp với **large-scale verification** và efficient proofs, nhưng tăng độ phức tạp triển khai, key/root governance và vận hành. Nếu không bảo vệ root hoặc không kiểm proof, tree chỉ là cấu trúc dữ liệu.

## 10. WORM, immutable storage và Object Lock

**WORM (Write Once, Read Many)** hoặc object immutability là các cơ chế hạn chế/sai khiến việc **ghi đè hoặc xóa bản lưu** trong khoảng thời gian retention trở nên không được phép hoặc bị kiểm soát chặt.

Một kiến trúc có thể dùng:
- Append-only log store hoặc journal có phân quyền.
- Object storage retention/Object Lock theo capability.
- Bucket/object versioning và protected archive.
- Immutable backup/recovery copy.
- Storage/retention policies có audit và separate administration.

### 10.1. Không đồng nhất “immutable” với “không ai xóa được”

Hiệu quả phụ thuộc:
- Chế độ retention/governance/compliance của sản phẩm.
- Ai có quyền sửa retention hoặc đặt legal hold.
- Cơ chế bypass/override được phép ở một số chế độ.
- Quyền xóa bucket/account, encryption key hoặc storage namespace.
- Bảo vệ service principal và cloud control plane.
- Chính sách pháp lý và vị trí lưu trữ.

**Cần xác minh cụ thể semantics của provider**, không suy rằng bật một checkbox “immutable” ngăn mọi kiểu xóa dữ liệu trong mọi tình huống.

### 10.2. Một storage account cho cả app và auditor có rủi ro

Nếu người quản trị sản xuất cũng được đổi log retention, xóa key mã hóa hoặc sửa archive, người đó có thể che dấu vết. Nên:
- Tách log archive vào security account/project/tenant phù hợp.
- Cho application **write-only/append-only** khi công nghệ hỗ trợ; không cho xóa/sửa lịch sử.
- Giới hạn quyền đọc PII theo nhu cầu.
- Có dual control/change approval cho retention, policy và key lifecycle.
- Audit và cảnh báo mọi thay đổi cơ chế immutable.

### 10.3. Immutable log vẫn có thể bị “đầu độc”

Một producer gửi event sai hoặc bịa đặt vẫn có thể được lưu bất biến. WORM bảo vệ **record đã nhận**, không chứng minh record phản ánh đúng hành động thực. Vì thế cần **đối soát independent signals** và bảo vệ nơi sinh log.

## 11. Tính đầy đủ: đếm, sequence, heartbeat và reconciliation

**Completeness** là thách thức riêng. Nếu attacker ngừng tạo log hoặc làm mất event trước khi được ký, mọi hash trên dữ liệu còn lại đều có thể hợp lệ.

### 11.1. Sequence numbers

Mỗi nguồn/partition có thể phát:
- `sourceId` và `streamId`.
- `sequenceNo` tăng theo thứ tự nguồn.
- `eventId` duy nhất.
- `previousHash`.
- `ingestReceivedAt`.
- `checkpointId`.

Nếu collector nhận sequence 201, 202, 204, cần điều tra **gap 203**, chứ không tự động đánh dấu integrity pass chỉ vì tất cả records nhận được có MAC hợp lệ.

### 11.2. Không cứ thiếu số là tấn công

Gaps có thể do:
- Producer restart và reset counter.
- Batch buffering/retry/duplication.
- Message queue partition và out-of-order delivery.
- Network outage.
- Event bị filter theo chính sách.
- Dữ liệu chưa đến do eventual consistency.

Phải định nghĩa **sequence epoch, partition, retry/deduplication, ordering window và source protocol** để tránh false positives.

### 11.3. Heartbeat

Một nguồn đáng tin có thể gửi **periodic heartbeat** hoặc collector kiểm **expected data rate/lastSeenAt**. Ví dụ IdP production thông thường gửi liên tục nhưng bỗng im lặng 30 phút khi hệ thống đang hoạt động: đây là một **gap đáng điều tra**, dù không thể khẳng định đã có event đăng nhập bị xóa.

### 11.4. Cross-system reconciliation

~~~text
HRIS: 1 Leaver event
IAM:  1 deprovision task
SCIM: 1 deactivate request
Target: 1 account state readback = inactive
PAM:  0 active privileged sessions
Audit: all links/correlation IDs present
~~~

Nếu IAM báo task succeeded nhưng target vẫn `active=true`, log integrity **không biến sai trạng thái thành đúng**. Sự khác biệt phải mở remediation hoặc incident, với logs có integrity giúp điều tra trách nhiệm và thời điểm.

## 12. Time integrity: thời gian nguồn khác thời gian collector

Đối với IAM, vài phút có thể quyết định **MFA enrollment, JIT expiry, Leaver SLA, token lifetime hoặc SoD violation**. Một event timestamp có thể bị chỉnh bởi host hoặc không đồng bộ.

### 12.1. Lưu ít nhất hai thời điểm khi có thể

| Trường | Ý nghĩa |
| --- | --- |
| `eventTime` | Mốc thời gian nguồn cho rằng sự kiện xảy ra. |
| `receivedAt` | Collector lần đầu nhận được sự kiện. |
| `processedAt` | Pipeline normalize/enrich/index event. |
| `effectiveAt` | Mốc nghiệp vụ quyền/assignment bắt đầu hoặc chấm dứt. |
| `verifiedAt` | Thời điểm target evidence được kiểm tra. |
| `sourceClockStatus` | Tín hiệu clock sync/offset nếu có. |

**Không dùng `receivedAt` làm thay thế vô điều kiện cho `eventTime`**; chúng mô tả hai việc khác nhau. Một event được gửi trễ vì offline collector vẫn có thể hợp lệ, nhưng cần giải thích delay.

### 12.2. Mốc chuẩn hóa và timezone

~~~text
eventTime  = 2026-11-23T10:05:00+07:00
receivedAt = 2026-11-23T03:05:02Z

Hai giá trị ở hai timezone tương đương
với độ trễ collector khoảng 2 giây.
~~~

Nên lưu instant có offset/UTC rõ và dùng nguồn thời gian đáng tin. Khi kiểm tra thứ tự event, cần đánh giá **clock skew, monotonic sequence và causal correlation**.

### 12.3. Timestamp được ký vẫn có thể sai

Một producer clock sai 15 phút vẫn có thể ký record bằng key hợp lệ. Chữ ký bảo vệ **thời gian được khai báo trong record** khỏi bị sửa sau đó; không tự chứng minh đồng hồ nguồn chính xác. Có thể bổ sung **trusted time source/collector receipt/checkpoint**, nhưng cần định nghĩa confidence và latency.

## 13. Schema event IAM phù hợp kiểm tra integrity

Một schema cần đủ metadata để truy vết nhưng không chứa bí mật.

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| **Identity** | `actorIdentityId`, `targetIdentityId`, `targetAccountId` | Định danh đúng người/account, tránh lệ thuộc email. |
| **Event** | `eventId`, `eventType`, `action`, `result` | Loại và outcome rõ ràng. |
| **Lifecycle** | `jmlPhase`, `effectiveAt`, `sourceAuthority` | Gắn với HRIS/Joiner–Mover–Leaver. |
| **Authorization** | `entitlementId`, `resourceScope`, `policyVersion` | Xác định quyền bị thay đổi. |
| **Review/approval** | `requestId`, `reviewDecisionId`, `approverIdentityId` | Đối chiếu quyền phê duyệt. |
| **Technical provenance** | `sourceSystem`, `streamId`, `sourceSequence` | Kiểm origin và gap. |
| **Correlation** | `correlationId`, `causationId`, `traceId` | Nối chuỗi hành động đa hệ thống. |
| **Timing** | `eventTime`, `receivedAt` | So sánh thời gian nguồn và collector. |
| **Integrity** | `canonicalizationVersion`, `previousHash`, `digest`, `signatureRef`, `keyId` | Kiểm chứng record/chain. |
| **Evidence** | `targetReadbackRef`, `verificationStatus` | Không đóng việc chỉ dựa vào API accepted. |

### 13.1. Phân biệt identity người và account kỹ thuật

Một operation có thể có:
- `actorIdentityId=person-2048` (người ra quyết định).
- `executorPrincipalId=scim-connector-prod` (machine identity thực thi).
- `targetAccountId=target-user-9008` (account bị gỡ quyền).
- `approverIdentityId=person-901` (người phê duyệt).
- `sourceSystem=scim-connector`.

Không gộp tất cả vào một trường `user` rồi mất nghĩa “ai làm gì”.

### 13.2. Event outcome phải mô tả thật

~~~text
REVIEW_DECIDED_REVOKE
SCIM_DEPROVISION_REQUEST_SENT
SCIM_DEPROVISION_RESPONSE_ACCEPTED
TARGET_ACCOUNT_READBACK_INACTIVE
SESSION_REVOCATION_VERIFIED
REVOCATION_VERIFIED_CLOSED
~~~

`REVIEW_DECIDED_REVOKE` khác `TARGET_ACCOUNT_READBACK_INACTIVE`. Log hoàn toàn nguyên vẹn nhưng dùng sai event semantics vẫn khiến kiểm toán hiểu sai.

## 14. JSON ví dụ: event gốc và metadata integrity

Một record minh họa:

~~~json
{
  "eventId": "evt-2026-11802",
  "eventType": "IAM_GROUP_MEMBERSHIP_REMOVED",
  "source": {
    "system": "scim-connector-prod",
    "streamId": "scim-outbox-03",
    "sequence": 881
  },
  "actor": {
    "executorPrincipalId": "workload-scim-connector",
    "requesterIdentityId": "person-2048"
  },
  "target": {
    "system": "analytics-app",
    "accountId": "user-9008",
    "groupId": "group-ops-admin",
    "tenant": "tenant-vn"
  },
  "authorization": {
    "approvalRef": "APR-2026-440",
    "policyVersion": "iam-access-v12"
  },
  "outcome": {
    "operation": "REMOVE_MEMBERSHIP",
    "result": "TARGET_CONFIRMED"
  },
  "time": {
    "eventTime": "2026-11-23T10:05:00+07:00",
    "receivedAt": "2026-11-23T03:05:02Z"
  },
  "correlationId": "JML-2026-3381",
  "integrity": {
    "schemaVersion": "identity-audit-v2",
    "canonicalizationVersion": "audit-c14n-v1",
    "previousDigestRef": "sha256:<previous-digest-placeholder>",
    "digestRef": "sha256:<digest-placeholder>",
    "signatureRef": "sig:<signature-placeholder>",
    "signingKeyId": "audit-signing-key-v3",
    "checkpointRef": "audit-checkpoint-2026-11-23-10"
  }
}
~~~

**Đây là schema nội bộ minh họa**, không phải format chuẩn của SCIM/OIDC/PAM. Các trường `digestRef/signatureRef` là placeholders, không phải bằng chứng mật mã hợp lệ. Trong triển khai thực tế phải quy định rõ **phần payload nào được ký**, tránh tính hash của chính trường chứa hash/signature (vòng lặp tự tham chiếu). Có thể đặt **payload và integrity envelope** thành hai đối tượng riêng.

### 14.1. Không đưa secrets vào event

Event nên giữ **reference ID** của credential chứ không lưu:
- Client secret plaintext.
- Password/OTP.
- OAuth access/refresh token đầy đủ.
- Authorization header.
- Private key, SSH private key.
- Session cookie hoặc recovery code.

Log có integrity cao mà chứa secrets thì trở thành **kho bí mật bị bảo toàn lâu dài**, rất khó xóa theo yêu cầu riêng tư/incident response.

## 15. Tách signed payload và integrity envelope

Để tránh vòng lặp hash, sử dụng mô hình:

~~~json
{
  "payload": {
    "eventId": "evt-2026-11802",
    "eventType": "ROLE_REVOKED",
    "subjectIdentityId": "person-2048",
    "targetAccountId": "user-9008",
    "eventTime": "2026-11-23T10:05:00+07:00"
  },
  "integrityEnvelope": {
    "algorithm": "SHA-256 + signature",
    "schemaVersion": "audit-v2",
    "sequence": 881,
    "previousDigest": "<previous-digest-placeholder>",
    "payloadDigest": "<payload-digest-placeholder>",
    "signingKeyId": "audit-key-v3",
    "signature": "<signature-placeholder>"
  }
}
~~~

### 15.1. Quy tắc cần được versioned

Một thiết kế đầy đủ cần xác định:
- Payload bytes/canonicalization.
- Field set/field order khi ký.
- Encoding, Unicode và number/date representation.
- Framing, algorithm và domain separation.
- Sequence/stream ID/previous digest được đưa vào dữ liệu ký hay không.
- Key ID, signature encoding.
- Schema migration và key rotation.
- Verification policy và trusted anchors.

Nếu đổi cách serialize mà không ghi version, log cũ có thể không verify được dù không ai sửa.

### 15.2. Integrity envelope không nên để writer sửa tự do

Nếu app có quyền cập nhật `integrityEnvelope.signature` sau khi ghi, cần đánh giá trust và anchor. Thiết kế tốt có thể để **collector/signer độc lập** tạo envelope/checkpoint sau khi nhận event, rồi lưu archive theo chính sách bất biến.

## 16. Java minh họa: HMAC cho canonical bytes có framing

Trong Java, có thể sử dụng các API chuẩn như `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec` và `java.security.MessageDigest`. Đoạn mã sau chỉ minh họa **cách tạo MAC cho một canonical event đã được chuẩn bị bên ngoài**; không phải một hệ thống log integrity hoàn chỉnh.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuditMac {
    private AuditMac() {}

    public static byte[] tag(
            byte[] key,
            String streamId,
            long sequence,
            byte[] previousDigest,
            byte[] canonicalEventBytes
    ) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));

        byte[] stream = streamId.getBytes(StandardCharsets.UTF_8);
        byte[] event = canonicalEventBytes;

        mac.update("IAM-AUDIT-V1".getBytes(StandardCharsets.US_ASCII));
        mac.update(ByteBuffer.allocate(4).putInt(stream.length).array());
        mac.update(stream);
        mac.update(ByteBuffer.allocate(8).putLong(sequence).array());

        mac.update(ByteBuffer.allocate(4).putInt(previousDigest.length).array());
        mac.update(previousDigest);

        mac.update(ByteBuffer.allocate(4).putInt(event.length).array());
        mac.update(event);

        return mac.doFinal();
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**
- `canonicalEventBytes` phải được tạo bởi **serializer canonical hóa có version**, không chỉ tùy tiện chuyển object sang chuỗi.
- `key` chỉ là tham số minh họa; trong hệ thống thật cần KMS/HSM/secret handling, giới hạn truy cập và rotation.
- Ví dụ tạo **MAC theo chuỗi** (đưa previous digest vào input), nhưng không tự tạo lưu trữ, checkpoint, verification hoặc nguồn đáng tin cho previous digest.
- Cần **xác minh MAC** bằng phương pháp so sánh phù hợp và quản trị key; không so chuỗi theo cách rò timing trong đường nhạy cảm.
- Chiều dài đầu vào, null/overflow, concurrency, epoch/partition, retries và DoS cần xử lý trong production.
- Không phát sinh raw secret, tag/nonce giả hoặc log plaintext key vào ứng dụng.
- Với audit pháp lý/độc lập, HMAC vẫn là symmetric proof, có thể cần **digital signatures và external anchor**.

### 16.1. Vì sao dùng length prefix?

Hai cặp dữ liệu `"ab"+"c"` và `"a"+"bc"` cùng tạo chuỗi bytes `abc` nếu chỉ nối trực tiếp. **Length prefix** làm input không mơ hồ. Khi chuỗi có nhiều fields, serialization phải đủ ràng buộc để không bị nhầm boundaries.

### 16.2. Không tự viết thuật toán mã hóa

Ví dụ chỉ minh họa cách gọi thư viện JDK. Không tự triển khai SHA-256/HMAC hoặc tự đặt thuật toán “băm kèm mật khẩu” tùy ý cho log. Hãy dùng **cryptographic libraries và dịch vụ signing/key management được duy trì**.

## 17. Verification: kiểm gì khi xác nhận log đáng tin?

Một verifier không nên chỉ so digest. Cần quy trình nhiều bước:

1. **Xác định scope**: stream, ngày, source, checkpoint, schema và key IDs.
2. **Tải raw evidence** từ nguồn/archived object có provenance.
3. **Kiểm anchor/checkpoint**: nguồn độc lập, signature/trust và thời điểm.
4. **Canonicalize đúng version** hoặc kiểm raw byte payload đúng như đã cam kết.
5. **Kiểm từng MAC/signature/hash-chain link**.
6. **Kiểm sequence range** và record count/gaps/duplicates.
7. **Kiểm stream transitions/rotations** và checkpoint continuity.
8. **Kiểm expected source heartbeat/ingestion** để phát hiện thiếu dữ liệu.
9. **So khớp các sự kiện trọng yếu** với independent HRIS/IdP/PAM/target readback.
10. **Lưu verification result** thành event riêng có kiểm soát.

### 17.1. Phân loại kết quả

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| **VERIFIED_INTACT** | Các điều kiện cryptographic và continuity trong phạm vi kiểm tra đều đạt. | Có thể dùng làm evidence trong phạm vi trust model. |
| **HASH_OR_SIGNATURE_MISMATCH** | Dữ liệu không khớp giá trị đã cam kết. | Containment, giữ raw copies, điều tra tampering/corruption. |
| **SEQUENCE_GAP** | Thiếu event/sequence theo kỳ vọng. | Kiểm buffer, retries, outage, suppression. |
| **MISSING_CHECKPOINT** | Không có anchor hoặc checkpoint cần thiết. | Không tuyên bố toàn vẹn vượt quá điểm được xác minh. |
| **UNTRUSTED_KEY_OR_SOURCE** | Không xác minh được origin/trust chain. | Không dùng làm chứng cứ xác thực nguồn. |
| **INSUFFICIENT_EVIDENCE** | Thiếu data hoặc semantics cần cho conclusion. | Ghi khoảng trống, thu thập thêm evidence. |
| **VERIFIED_BUT_INCOMPLETE** | Cryptographic proof pass nhưng cross-system gap còn. | Mở investigation/reconciliation. |

Đây là các **trạng thái minh họa**, không phải enum chuẩn của nền tảng IAM hay SIEM.

### 17.2. Không “pass” im lặng khi verifier lỗi

Nếu verifier không thể đọc key, không giải mã được schema hoặc không có anchor, phải báo **verification unavailable/failed** theo policy; không gắn “PASS” chỉ vì không phát hiện mismatch.

## 18. State machine cho log ingestion và verification

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> TRANSMITTED: authenticated source
    TRANSMITTED --> RECEIVED: collector ack
    RECEIVED --> SEALED: signed or MAC/checkpoint
    SEALED --> ARCHIVED: retention/immutability
    ARCHIVED --> VERIFICATION_PENDING
    VERIFICATION_PENDING --> VERIFIED_INTACT: chain + anchor + continuity passed
    VERIFICATION_PENDING --> GAP_DETECTED: missing sequence or heartbeat
    VERIFICATION_PENDING --> TAMPER_SUSPECTED: hash or signature mismatch
    GAP_DETECTED --> INCIDENT_INVESTIGATION
    TAMPER_SUSPECTED --> INCIDENT_INVESTIGATION
    INCIDENT_INVESTIGATION --> REMEDIATION_REQUIRED
    VERIFIED_INTACT --> [*]
~~~

Trong thực tế có thể ingest theo batch hoặc event streaming, và một event đã archived có thể được **verify nhiều lần** khi điều tra. Một “VERIFIED” ở thời điểm T không chứng minh toàn bộ sự kiện tương lai đều có integrity.

### 18.1. Invariants quan trọng

- App producer không được tùy ý **xóa/chỉnh lịch sử đã seal**.
- Key writer không mặc nhiên là key kiểm toán độc lập.
- Mọi thay đổi log pipeline/retention phải có **audit trail riêng**.
- Audit stream phải gắn **identity của nguồn và phạm vi**.
- Records bị replay/dedup phải được xử lý có dấu vết, không xóa thầm.
- Hệ thống không được coi `REQUEST_ACCEPTED` là `ACTION_VERIFIED`.
- Log verifier failure không bị biến thành success khi backend timeout.
- Thu hồi quyền quản trị log của Leaver phải được kiểm chứng trên **control plane và storage**.

## 19. Truyền log: TLS/mTLS, buffering và chống mất dữ liệu

### 19.1. Transport authentication

TLS bảo vệ **kênh truyền** chống đọc/sửa giữa các endpoints được xác thực. mTLS có thể hỗ trợ chứng thực **collector và agent**. Cần:
- Kiểm CA/trust và tên endpoint, không bỏ certificate validation.
- Định danh machine identity của producer/agent.
- Giới hạn nơi/port nhận log.
- Quản lý certificate/key rotation.
- Không dùng mTLS như bằng chứng rằng nội dung producer gửi là đúng sự thật.

### 19.2. Queue và at-least-once delivery

Nhiều log pipelines dùng **at-least-once delivery** để tránh mất event. Một event có thể được gửi lại, vì vậy cần `eventId`, source sequence, dedup và idempotency. **Duplicate không mặc nhiên là tampering**.

Nếu thiết kế at-most-once, một số failures có thể làm mất event; nếu dùng exactly-once semantics ở một lớp, cũng cần đánh giá **end-to-end** từ producer đến archive — không suy đúng toàn tuyến chỉ vì queue quảng cáo exactly-once.

### 19.3. Buffer đầy hoặc agent bị dừng

Đặt rõ:
- Buffer size, disk persistence và backpressure.
- Chính sách khi không gửi được: giữ cục bộ, drop? Nếu drop, ghi counters và alert.
- Sự kiện nhạy cảm nào phải ưu tiên?
- Khi service restart, khôi phục sequence/offset/checkpoint thế nào?
- Cách biết tổng events đã sinh so với đã nhận?
- Có thể bị attacker cố tình làm đầy queue không?

### 19.4. Không log secret trong error stack

Khi exporter lỗi, log retry không được in nguyên HTTP headers chứa access token, client secret hoặc session cookie. Integrity không chữa được credential leak; nó chỉ giữ vết bị lộ lâu hơn.

## 20. Quyền truy cập log và Separation of Duties

Một ứng dụng hoặc admin có thể có khả năng **gây ra** sự kiện IAM; nếu cũng có quyền **xóa log của chính sự kiện đó**, nguy cơ che giấu tăng.

### 20.1. Tách trách nhiệm

| Vai trò | Quyền cần | Tránh |
| --- | --- | --- |
| **Application/connector** | Gửi/append events vào collector. | Delete/overwrite history, đổi retention. |
| **Log collector** | Ingest, normalize theo rule, seal/checkpoint. | Tự vô hiệu hóa kiểm chứng mà không audit. |
| **Security operations** | Query/alert/investigate trong scope. | Tự tắt nguồn audit mà không có change governance. |
| **Audit/compliance** | Read/verifying evidence, kết quả độc lập. | Có quyền forge producer records hoặc ký tùy tiện. |
| **Platform admin** | Vận hành hạ tầng theo runbook. | Mặc định có thể sửa nội dung/chữ ký/history. |
| **Key custodian** | Quản lý signing keys/rotation. | Có cả quyền chỉnh log và xóa audit key history không kiểm soát. |
| **Retention/legal owner** | Phê duyệt thời hạn/hold/deletion hợp lệ. | Bypass policy bằng sửa file thủ công. |

### 20.2. RBAC/ABAC cho dữ liệu log

Log IAM có thể chứa identity ID, IP, device, app IDs và security-sensitive metadata. Cần:
- **Least privilege** cho read/query/export.
- Scope theo team/tenant, mục đích điều tra và classification.
- MFA/PAM/JIT cho thao tác administrative với log archive.
- SoD giữa người quản trị hệ thống được giám sát và người xác minh evidence.
- Logging chính hành động **xem/tải/export/xóa/đổi retention** log.
- Approved exception có owner/time limit và review.

### 20.3. Không coi “read-only SIEM” là đủ

Một auditor có thể không sửa query results nhưng log source bị tắt trước đó, hoặc storage checkpoint bị thay. **Khả năng chỉ đọc** của dashboard không tự bảo đảm sự đáng tin của dữ liệu.

## 21. Retention, legal hold và quyền riêng tư

Log integrity thường đi cùng nhu cầu giữ evidence lâu, nhưng không được dùng retention vô hạn cho mọi dữ liệu.

### 21.1. Những yêu cầu cần cân bằng

- Audit/regulatory retention obligations.
- Security incident investigation needs.
- Data minimization và purpose limitation.
- Quyền truy cập và thời gian lưu PII.
- Legal hold hoặc preservation khi có tranh chấp/sự cố.
- Cost/availability và khả năng restore.
- Cryptographic key retention đủ để verify records cũ.

Không có **một số năm retention phổ quát** áp dụng cho mọi module IAM hoặc mọi quốc gia. Policy cần căn cứ pháp lý, risk và hệ thống.

### 21.2. Xóa đúng quy trình khác tampering

Có trường hợp log được phép xóa khi hết retention và không thuộc legal hold. Điều đó **không phải thao tác gian lận** nếu:
- Xóa đúng policy đã phê duyệt.
- Quyết định, scope, actor và deletion event được audit.
- Không còn hold/lệnh bảo toàn evidence.
- Archive/verifier biết segment đã được retired hợp lệ.
- Chain/checkpoint/manifest được quản lý để không nhầm “deletion hợp lệ” thành gap bất thường.

### 21.3. Không dùng immutable storage để lưu secrets vô hạn

Trước khi vào archive, phải **mask/remove** secrets và PII không cần. Với dữ liệu đã vô tình đi vào WORM, cần incident response, access containment và quy trình xử lý theo pháp lý/capability — không tự “xóa lén” để tránh breach evidence.

## 22. Hash/key rotation và tính liên tục của log qua thời gian

Log integrity tồn tại qua nhiều năm có thể gặp:
- Signing key rotation.
- Certificate expiry.
- Algorithm migration.
- Schema/canonicalization upgrades.
- Log partition rollover.
- Storage migration.
- Ownership/tenant changes.
- Mất key hoặc nghi compromise.

### 22.1. Ràng buộc key ID và epoch

Một record/checkpoint cần biết:
- `algorithm` và `canonicalizationVersion`.
- `signingKeyId` hoặc `macKeyId`.
- Key validity window.
- Issuer/identity tin cậy của signer.
- Stream/sequence range.
- Parent/previous checkpoint.
- Timestamp và verification metadata.

### 22.2. Rotate mà vẫn verify lịch sử

Khi thay V1 → V2:
1. Đóng batch/epoch cũ bằng checkpoint được bảo vệ.
2. Ký metadata chuyển epoch/stream nếu cần.
3. Kích hoạt V2 cho events mới.
4. Chặn V1 ký thêm events ngoài policy.
5. Giữ public verification material/khả năng verify V1 logs trong retention.
6. Kiểm tra chain continuity qua mốc chuyển.
7. Audit người thực hiện rotation và policy approvals.

### 22.3. Key compromise làm giảm độ tin cậy lịch sử

Nếu signing private key bị lộ:
- Khóa/issuer cần revoke/rotate theo khả năng.
- Xác định phạm vi records và thời gian có thể bị forge.
- Dùng **external anchors/checkpoints đã tồn tại trước compromise** để thu hẹp vùng không chắc.
- Cross-verify với log độc lập của HRIS, target, IdP hoặc PAM.
- Không tuyên bố mọi record từng ký bằng key đó đều chắc chắn giả; nhưng **mức assurance phải điều chỉnh**.

## 23. Tích hợp JML: minh chứng Joiner, Mover, Leaver

### 23.1. Joiner — log tạo account và cấp quyền ban đầu

Một Joiner có thể tạo event:
- `IDENTITY_PROOFING_COMPLETED`.
- `ACCOUNT_CREATED` tại IdP.
- `MFA_ENROLLED`.
- `ROLE_ASSIGNED` theo baseline/approval.
- `TARGET_PROVISIONING_VERIFIED`.

Integrity giúp phát hiện thao tác sửa evidence về **ai cấp quyền, lúc nào, dựa vào manager/HR source nào**. Nhưng một log giữ nguyên vẫn không chứng minh role là least privilege; cần policy và review.

### 23.2. Mover — phát hiện role accumulation

Lan chuyển từ Operations sang Finance:
- HRIS event đổi assignment có effectiveAt.
- IAM tính `REMOVE OpsAdmin`, `GRANT FinanceReader`.
- Connector gửi SCIM/PAM changes.
- Target readback xác nhận OpsAdmin không còn.
- Access review xử lý những exceptions chưa hết.

Nếu admin xóa event `OpsAdmin REVOKE FAILED`, hash-chain/checkpoint hoặc independent target query có thể phát hiện sai lệch. **Không để event approval của Finance che lấp việc quyền Ops còn tồn dư**.

### 23.3. Leaver — bằng chứng phải theo đích

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as IAM / IGA
    participant IDP as IdP / SSO
    participant APP as Target SaaS / SCIM
    participant PAM as PAM
    participant LOG as Audit collector / archive
    HR->>IAM: Leaver event + effectiveAt
    HR-->>LOG: HR source event
    IAM->>IDP: Disable account
    IDP-->>LOG: Account disable outcome
    IAM->>APP: SCIM deprovision
    APP-->>LOG: Target response/readback
    IAM->>PAM: Revoke privilege + sessions
    PAM-->>LOG: Session/credential verification
    IAM-->>LOG: Reconciliation + final closure decision
    LOG->>LOG: Seal + checkpoint + independent verification
~~~

**Không giả định mọi component tự gửi logs trực tiếp**; sơ đồ mô tả các loại evidence cần có. Sự khác nhau giữa `request accepted` và `target effective denied` phải còn nguyên trong chain.

### 23.4. Human Leaver và machine identity vẫn hoạt động

Người từng sở hữu `billing-etl` nghỉ, nhưng job vẫn chạy. Evidence cần:
- HR Leaver event.
- Thu hồi human vault/CI/CD/app-admin privileges.
- Owner handover cho workload.
- Credential exposure review/rotation nếu cần.
- Job tiếp tục có app-only quyền hợp lệ.
- Không còn direct personal token hoặc impersonation path của người cũ.

Một log “service account deleted” không phải kết quả bắt buộc và thậm chí có thể là sự cố nếu workload vẫn cần thiết.

## 24. IdP/SSO, OAuth/OIDC và SCIM: liên kết nhưng không tin một nguồn

### 24.1. IdP/SSO logs

Có thể ghi:
- Login success/failure.
- MFA challenge/step-up.
- Session creation/revocation.
- Conditional access decision.
- App assignment/group change.
- Admin policy/client registration change.

Các event giúp truy vết **authentication**, nhưng không chứng minh một API ở downstream đã cho phép hay từ chối một action — cần target authorization logs.

### 24.2. OAuth/OIDC logs

Các event cần quan tâm:
- Token issued: client ID, grant type, scope/audience, token reference, expiry.
- Client authentication failed.
- Client secret rotated/revoked.
- Refresh token/grant revoked.
- Admin consent hoặc app-only role changed.

**Không ghi toàn bộ OAuth token, client secret hay Authorization Basic header**. Token IDs/references đủ để liên kết event theo policy, tránh credential exposure.

### 24.3. SCIM provisioning logs

Mỗi request/response quan trọng nên phân biệt:
- Client/connector identity.
- Target URL/resource ID.
- Operation Create/PATCH/DELETE.
- Request correlation ID.
- Result/status, retry/timeout semantics.
- Target readback khi cần.

**SCIM HTTP 200/204 không tự bằng chứng account hết quyền trên mọi đường**; một local role hoặc session/token có thể còn. Integrity bảo vệ trace thực hiện; **reconciliation** mới xác nhận desired vs actual.

### 24.4. Không tin đồng hồ hay bản tóm tắt của một nguồn duy nhất

IdP, SCIM connector và target có thể có clock skew khác nhau. Giữ nguồn/timestamp/receivedAt riêng; dùng correlation và sequence để hiểu chuỗi, không tạo timeline chắc chắn chỉ từ một trường ngày.

## 25. PAM/JIT và Emergency access: log quan trọng hơn khi quyền cao

Đặc quyền có khả năng sửa log thì **phải bảo vệ evidence ngoài tầm quyền thông thường của người dùng đặc quyền đó**.

Một emergency access case có thể cần:
- Incident/request ID và lý do.
- Beneficiary person identity.
- Break-glass credential checkout/custody.
- PAM eligibility/activation và duration.
- Session start/end và session ID.
- Command/action audit hoặc recording reference.
- Role/group/credential grants thay đổi.
- Approval/SoD exception decision (nếu hợp lệ).
- Session/token/credential revoke.
- Independent post-use review.

### 25.1. Session recording không thay log integrity

Một video/recording có thể bị cắt ghép hoặc xóa nếu lưu trên cùng host do operator kiểm soát. Với dữ liệu quan trọng, cần **file digest, capture metadata, checkpoint/immutable archive, access controls và chain of custody**. Video được ghi cũng không chứng minh không có command ngoài camera nếu nhiều access paths tồn tại.

### 25.2. Break-glass khi collector offline

Nếu IdP/PAM/log collector không hoạt động, phải có **quy trình evidence dự phòng**:
- Ai truy xuất recovery credential?
- Có manual/independent witness theo policy?
- Những timestamps và tài nguyên nào được ghi?
- Hệ thống nào còn lưu target-side actions?
- Khi phục hồi, nhập evidence với **createdAt và importedAt khác nhau**.
- Ghi khoảng thời gian không thể chứng minh continuity.
- Đối soát sự kiện với target changes, không giả mạo log “đã có từ trước”.

### 25.3. Không để emergency admin tự xóa hậu kiểm

Một emergency role không nên mặc định có quyền xóa/đổi retention archive chứa log chính hành động của họ. Nếu bắt buộc có quyền quản trị hạ tầng log để khôi phục, cần separate evidence/anchor và independent review.

## 26. RBAC/ABAC và log policy changes

**Authorization decisions** có thể phụ thuộc RBAC, ABAC và điều kiện môi trường. Các event đáng log:

~~~text
ROLE_CREATED / ROLE_UPDATED / ROLE_DELETED
USER_ROLE_ASSIGNMENT_ADDED / REMOVED
GROUP_MEMBERSHIP_ADDED / REMOVED
RESOURCE_POLICY_CHANGED
ABAC_RULE_VERSION_CHANGED
PAM_ELIGIBILITY_GRANTED / REVOKED
SOD_EXCEPTION_APPROVED / EXPIRED
AUTHZ_DECISION_DENY / PERMIT (theo sampling/risk)
~~~

### 26.1. Không ghi toàn bộ PII hay payload cho mọi decision

Một hệ thống API rất lớn không nhất thiết cần lưu mọi request body. Có thể:
- Log decisions nhạy cảm hoặc actions có tác động lớn.
- Thực hiện sampling có chính sách và ghi rõ sampling metadata.
- Lưu `policyVersion`, `subjectId`, `action`, `resourceRef`, `decision`.
- Giữ trace/correlation ID.
- Bảo vệ logs phục vụ incident response.

**Sampling làm giảm khả năng chứng minh completeness tuyệt đối**; cần nêu rõ giới hạn trong audit claims.

### 26.2. Policy drift và log integrity

Nếu ABAC rule được sửa nhưng event `POLICY_CHANGED` bị mất, audit không thấy tại sao hành động từng Deny nay Permit. Cần **config change log**, phân quyền sửa policy, independent version control khi thích hợp và verifier kiểm event pipeline.

### 26.3. SoD trong audit

Người có quyền cấp `GlobalAdmin` không nên đồng thời có thể:
- Tắt audit.
- Thay audit event schema để bỏ actor.
- Xóa log retention.
- Thay signing key và checkpoint không để lại evidence.
- Tự xác nhận verification success khi bị nghi ngờ sửa log.

Đây là **đường xung đột phân tách nhiệm vụ** cần xét trong IAM/IGA.

## 27. Logging cho non-human account và machine identity

Một machine identity có thể được dùng trong:
- OAuth Client Credentials grant.
- Workload federation.
- mTLS kết nối API.
- CI/CD deployment.
- Kubernetes ServiceAccount.
- Service account ở database.
- Automation/bot/RPA.

Một event chất lượng nên gắn:
- Logical workload identity.
- Runtime/workload instance reference nếu đáng tin.
- OAuth client/service principal ID.
- Issuer/trust domain, credential reference (không secret).
- Target resource/action và authorization outcome.
- Owner team/business service.
- Pipeline/job/version khi liên quan.
- Correlation ID và signing/source metadata.

### 27.1. Shared credentials làm attribution yếu

Nếu ba jobs dùng `svc-data-admin`, log “svc-data-admin SELECT” chưa chắc phân biệt job nào thực hiện. Hash/signature có thể chứng minh record không bị sửa, **nhưng không biến shared identity thành attribution của từng job**. Cần tách workload identities/credentials hoặc gắn job context qua nguồn tin cậy.

### 27.2. Machine identity bị retire

Khi service retired, logging cần chứng minh:
- Client/role/grant bị revoke.
- Key/cert/client secret không còn hợp lệ.
- Scheduled job và trust mapping đã xử lý.
- Token/session còn sống được đánh giá.
- Target không còn effective access.
- Owner/auditor đã xác nhận closure.

Nếu không còn event vì service không chạy, **không tự suy “không còn quyền”**. Hãy đọc actual target state.

## 28. Case study A — Admin cố xóa dấu vết cấp GlobalAdmin

**Bối cảnh:** Một admin được cấp quyền quản trị IdP để sửa sự cố, sau đó tự gán `GlobalAdmin` lâu hơn thời hạn. Admin có quyền xem local audit file trên cùng server.

### 28.1. Kiến trúc yếu

~~~text
IdP writes local audit.log
Admin has administrator/root permissions on host
SIEM periodically reads audit.log once per day
No external checkpoint or heartbeat
~~~

Admin sửa/xóa `ROLE_GRANTED` trước khi SIEM đọc. SIEM có thể không bao giờ biết event đã tồn tại, và hash tính sau khi sửa sẽ xác nhận **bản đã bị thay đổi** chứ không phải bản gốc.

### 28.2. Kiến trúc tăng khả năng phát hiện

- IdP stream events tới collector độc lập ngay khi có thể.
- Collector xác thực nguồn, cấp ingest sequence/receipt timestamp.
- Archive được phân quyền tách khỏi IdP admin.
- Batch digest/hash chain được ký/anchor ngoài quyền người dùng sản xuất.
- Heartbeat và log-source status alert khi IdP không gửi.
- IdP role assignments được đối soát qua API độc lập.
- `LOG_CONFIG_CHANGED` và `ROLE_GRANTED` đều được giám sát.
- Audit review phân biệt grant accepted, actual role và expiry.

### 28.3. Kết luận đúng mức

Nếu local file đã bị sửa **trước khi collector nhận**, archive không thể phục hồi một event chưa từng nhận. Nhưng **role readback, IdP target audit, directory changes hoặc các independent signals** có thể phát hiện quyền bất thường. Thiết kế nên làm giảm **time-to-collection** và tăng nguồn xác thực chéo.

## 29. Case study B — Leaver bị báo hoàn tất nhưng session còn sống

**Bối cảnh:** HRIS gửi Leaver cho Lan, IAM disable IdP User, SCIM target trả 204, dashboard ghi “Offboarding completed”. Một OAuth refresh token và app local session vẫn còn được dùng.

### 29.1. Vì sao log integrity chưa đủ?

Mọi event có thể có signature hợp lệ, nhưng workflow ghi kết luận sai vì chỉ nhìn **IdP và SCIM API result**, không kiểm target session/token. Đây là lỗi **semantic correctness và verification coverage**, không phải cryptographic tampering.

### 29.2. Evidence chain cần có

~~~text
HR_LEAVER_CONFIRMED
  -> IAM_DEPROVISION_TASK_CREATED
  -> IDP_ACCOUNT_DISABLED
  -> SCIM_TARGET_DEACTIVATED
  -> APP_SESSION_INVALIDATION_REQUESTED
  -> OAUTH_REFRESH_TOKEN_REVOKED
  -> TARGET_EFFECTIVE_ACCESS_DENIED
  -> OFFBOARDING_VERIFIED_CLOSED
~~~

Mỗi event cần nguồn, identity binding, correlation/time và integrity protection. Nếu ứng dụng không hỗ trợ session revoke tức thời, ghi **residual access window/containment** thay vì “Verified”.

### 29.3. Không sửa lịch sử để làm dashboard đẹp

Nếu closure được ghi sai, phát **CORRECTION/RETRACTION event** trỏ tới event gốc và giải thích sai lệch, rồi mở remediation. **Không sửa/xóa event cũ** trong archive. Append-only evidence cho phép audit thấy sự thay đổi kết luận.

## 30. Case study C — Log collector mất mạng 25 phút

**Bối cảnh:** SCIM connector chạy liên tục, collector bị network partition từ 11:00 đến 11:25. Sau phục hồi, một phần events được replay.

### 30.1. Các khả năng

- Agent buffer đủ và gửi lại tất cả → **ingest delay**, không mất event.
- Buffer đầy và drop records → **sequence gap**.
- Agent restart và reset counter → cần **epoch/partition metadata** để phân biệt.
- Một event bị gửi hai lần → duplicate hợp lệ của at-least-once delivery.
- Attacker chủ động tắt collector → cần điều tra log source/infra changes.

### 30.2. Cách kiểm chứng

1. Kiểm source/stream IDs và sequence/epoch.
2. Đối chiếu producer counters với collector receipts.
3. Kiểm duplicate IDs và reorder window.
4. Verify chain/signature và external checkpoint.
5. Kiểm heartbeat, lag, drop counters.
6. So SCIM operations với target readback.
7. Nếu thiếu events, đánh dấu evidence gap và remediation, không dựng records giả để “lấp” chuỗi.

### 30.3. Resilience cần cân bằng

Một hệ thống IAM có thể ưu tiên availability khi audit sink lỗi, nhưng quyền đặc biệt có thể cần yêu cầu logging chặt hơn. **Fail-open/fail-closed khi logging không hoạt động** phải được chính sách rủi ro xác định theo action/impact; không có một lựa chọn phù hợp cho mọi ứng dụng.

## 31. Kịch bản response khi phát hiện log tampering

Khi verifier phát hiện mismatch hoặc SIEM bị nghi sửa/xóa:

1. **Phân loại mức độ tin cậy còn lại**: source nào, stream nào, khoảng thời gian nào, checkpoint cuối đáng tin ở đâu.
2. **Bảo toàn evidence**: raw archive, snapshots, signed roots, key/audit events, time references theo khả năng và pháp lý.
3. **Không ghi đè nguồn** bằng “sửa hash cho khớp” hoặc xóa đoạn lỗi.
4. **Hạn chế đường thay đổi**: cô lập credential/session/role nghi compromise theo playbook.
5. **Kiểm signing key và storage admin changes**, đánh giá key compromise.
6. **Thu thập independent evidence** từ HRIS, IdP, SCIM target, PAM, cloud API, DB logs, network/security telemetry.
7. **Đối soát IAM state**: roles, group membership, privileged sessions, tokens, service credentials và Leaver status.
8. **Xác định root cause**: bug serialization, outage, sequence handling, malicious tampering, key misuse.
9. **Khôi phục pipeline và trust boundary**, rotate/revoke keys nếu cần.
10. **Re-run verification** và ghi mới một kết luận incident có scope, limitations, sign-off.
11. **Cập nhật detections/tests** để tránh tái diễn.

### 31.1. Chain of custody

Để dùng chứng cứ trong điều tra chính thức, ghi:
- Ai thu evidence, lúc nào, bằng phương tiện gì.
- Nguồn gốc/địa điểm/IDs.
- Digest/checkpoint/signature của artifact thu thập.
- Ai đã đọc/copy/chuyển/giải mã.
- Bản gốc và bản phân tích khác nhau thế nào.
- Những transforms được phép và tool/version.
- Điều gì chưa thể chứng minh.

**Một hash tự tính sau khi lấy file** chỉ chứng minh file không đổi **kể từ thời điểm tính hash** (nếu digest bảo vệ), không chứng minh nó không bị sửa trước đó.

### 31.2. Không kết luận chỉ từ một mismatch

Mismatch có thể do:
- Lỗi canonicalization hoặc schema version.
- Encoding/normalization.
- Truncated transmission.
- Key rotation dùng sai version.
- Dữ liệu hỏng.
- Thao tác sửa đổi có chủ đích.

Mọi trường hợp đều cần điều tra, nhưng không nên tuyên bố chắc chắn “attacker xóa log” khi chưa có bằng chứng.

## 32. Ma trận kiểm thử log integrity

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **T1** | Sửa một byte trong payload đã seal. | Hash/signature verification fail. |
| **T2** | Xóa một event giữa stream. | Chain/sequence gap detected. |
| **T3** | Đảo thứ tự hai events cùng stream. | Sequence/chain invalid. |
| **T4** | Replay event đã nhận. | Duplicate event ID/sequence identified. |
| **T5** | Cắt toàn bộ suffix sau checkpoint. | Checkpoint/heartbeat/expected continuity báo thiếu. |
| **T6** | Sửa event và tính lại digest local. | External anchor/signature độc lập phát hiện nếu trust assumptions đúng. |
| **T7** | Producer không gửi event nhưng không sửa cái đã gửi. | Heartbeat/cross-system reconciliation phát hiện gap có thể có. |
| **T8** | Clock nguồn lệch 10 phút. | EventTime–receivedAt skew cảnh báo; không giả total order. |
| **T9** | Collector offline rồi replay queue. | Dedup/gap recovery, ghi ingest delay. |
| **T10** | Schema canonicalization đổi mà không version. | Verification fail; rollback/sửa migration đúng quy trình. |
| **T11** | Key V1 đã rotate, log cũ cần verify. | Verify được bằng historical trust material theo retention. |
| **T12** | Signing key nghi compromised. | Thu hẹp assurance scope, incident/rotation/independent checks. |
| **T13** | Người có app admin thử xóa archive. | Bị chặn theo policy; security alert/audit. |
| **T14** | Retention config bị sửa. | Independent change event + approval/alert. |
| **T15** | SIEM query projection bị sửa. | Raw/archive digest vẫn verify; projection diff được phát hiện. |
| **T16** | SCIM ghi success nhưng target account active. | Correctness/reconciliation fail dù signature pass. |
| **T17** | Leaver session tồn dư sau disable. | Residual-access incident/remediation, không VerifiedClosed. |
| **T18** | Shared service account gây khó attribution. | Thể hiện hạn chế evidence; đề xuất identity separation. |
| **T19** | Token/secret vô tình nằm trong log. | Secret scanning alert, containment và data handling. |
| **T20** | Legal retention kết thúc, record được xóa hợp lệ. | Deletion có approval/audit và manifest, không nhầm silent tampering. |
| **T21** | Merkle inclusion proof hợp lệ nhưng một event khác thiếu. | Integrity proof pass, completeness chưa đủ; gap check vẫn fail. |
| **T22** | Break-glass khi SIEM offline. | Manual/alternate evidence với truthful timestamps và hậu kiểm. |
| **T23** | Một writer ký record giả nhưng signer hợp lệ. | Signature pass; independent business/target evidence phát hiện inconsistency. |
| **T24** | Verifier không truy cập key/checkpoint. | INSUFFICIENT_EVIDENCE/verification error, không tự pass. |
| **T25** | Writer có thể sửa retention và HMAC key. | SoD/security design review fail, cần độc lập trust. |
| **T26** | Dùng cache dashboard ẩn alert mới. | Independent archive/event receipt vẫn xác nhận được. |

### 32.1. Positive và negative verification

- **Positive:** log được phát đúng, lưu đúng, verify nguyên vẹn, truy xuất trong retention.
- **Negative:** sửa/xóa/chèn/đảo/replay bị phát hiện trong threat model.
- **Resilience:** outage/retry không làm log giả hoặc silent drop.
- **Operational:** key rotation, schema migration, legal deletion có bằng chứng.
- **IAM-specific:** JML/IdP/SCIM/PAM events có thể đối chiếu tới actual access và quyền thu hồi.

## 33. KPI và SLO cho tính toàn vẹn nhật ký

| Chỉ số | Định nghĩa tham khảo | Cạm bẫy |
| --- | --- | --- |
| **Integrity verification coverage** | Tỷ lệ batch/streams được xác minh theo policy. | 100% batch verify không chứng minh producer completeness. |
| **Verification failure count** | Mismatch hoặc lỗi trust per source/time. | Tách lỗi config/serialization với tampering nghi vấn. |
| **Sequence gap count** | Khoảng số thứ tự thiếu theo stream/epoch. | Có thể do retry/repartition hợp lệ, cần triage. |
| **Missing heartbeat/source silence** | Nguồn không gửi event trong khoảng kỳ vọng. | Những nguồn ít hoạt động cần heartbeat riêng. |
| **Ingest lag** | Chênh `receivedAt - eventTime` theo nguồn. | Clock skew làm số liệu sai. |
| **Archive coverage** | Events/streams có bản lưu immutable + anchor. | Không chỉ có SIEM index. |
| **Anchor/checkpoint compliance** | Checkpoints được lưu/verify đúng lịch. | Anchor nằm cùng quyền writer chưa độc lập. |
| **Unowned log sources** | Nguồn log không có owner/schema/retention. | Khó điều tra integrity gap. |
| **Privileged log-access anomalies** | Truy vấn/export/config changes bất thường. | Cần lý do/approval và account identity đúng. |
| **Log pipeline config drift** | Thay đổi filter/retention/key/agent trái desired state. | Không đo chỉ bằng số events đến. |
| **JML evidence completeness** | Leaver/Mover có đủ approval, action, target readback. | Một event “completed” không thay target verification. |
| **Time-to-detect tampering** | Từ dấu hiệu đầu tới alert/triage. | Đo theo trusted timestamps và điều kiện source. |
| **Verification recovery time** | Thời gian khôi phục trust sau mismatch/outage. | “Khắc phục dashboard” không đủ. |
| **Residual privilege after verified event** | Trường hợp log ghi revoked nhưng quyền thực tế còn. | Phải kết hợp independent target probes/readback. |
| **Evidence access audit coverage** | Đọc/export/hold/delete log có truy vết. | Integrity không thay confidentiality/privacy. |

Đặt ngưỡng theo **rủi ro tài nguyên, tần suất event, retention, khả năng telemetry và policy nội bộ**. Không có một tỷ lệ mặc định đúng cho mọi tổ chức.

## 34. Những anti-patterns phổ biến

| Anti-pattern | Vì sao không đủ | Hướng xử lý |
| --- | --- | --- |
| Tính SHA-256 rồi lưu hash trong cùng file sửa được. | Attacker sửa cả nội dung và hash. | Signature/anchor độc lập, archive protected. |
| Coi TLS là log integrity từ đầu tới cuối. | TLS chỉ bảo vệ kênh giữa endpoints. | Source trust, storage/key governance và verification. |
| Chỉ bật immutable storage mà không kiểm producer. | Event sai/thiếu được lưu bất biến. | Independent source reconciliation, heartbeats. |
| App admin có quyền delete logs. | Tự che dấu hành vi. | Separate account/project/role, SoD. |
| SIEM dashboard là evidence gốc duy nhất. | Query/index có thể bị sửa hoặc hết retention. | Raw immutable archive + verifiable references. |
| Hash chain không có checkpoint ngoài quyền writer. | Có thể viết lại toàn bộ lịch sử và hash. | Signed external anchors. |
| Chỉ kiểm content, không kiểm sequence. | Xóa một record có thể khó thấy trong vài kiểu lưu. | Per-stream sequencing/gap alerts. |
| Chỉ kiểm signature và coi event đã đúng. | Producer có thể ký nội dung sai. | Target readback và cross-source verification. |
| Coi authentication log là bằng chứng AuthZ tại mọi API. | App có direct grants/local sessions. | PEP/resource logs + correlation. |
| Ghi `REVOKED` ngay khi PATCH accepted. | Closure sai ngữ nghĩa. | Tách request/response/readback/verified. |
| Gộp sourceTime và receivedAt. | Che ingestion lag/clock skew. | Hai timestamps và time sync. |
| Rà soát log bằng shared admin account. | Mất person attribution. | Named accounts, PAM, identity binding. |
| Đổi signing key mà không lưu key ID/version. | Log cũ không verify được. | Key inventory/rotation/checkpoints. |
| Giữ full JWT/client secret trong audit. | Log thành kho credential. | Redaction và reference IDs. |
| Xóa record gốc rồi thay bằng record “sửa”. | Mất forensic history. | Append-only correction/retraction events. |
| Không ghi sự kiện tắt audit/đổi retention. | Attacker tắt capture mà không có dấu vết. | Protected control-plane audit. |
| Auto-pass khi verifier timeout. | Báo cáo sai assurance. | Verification error/insufficient evidence. |
| Immutability mà không có backup/recovery test. | Archive không truy xuất được. | Durability/availability tests. |
| Bỏ nguồn có ít events khỏi monitoring. | DR/break-glass identity không có audit readiness. | Heartbeat/source ownership và kiểm thử định kỳ. |
| Chỉ nhìn log để kết luận Leaver hoàn thành. | Residual access có thể tồn tại. | Actual target reconciliation. |

## 35. Checklist thiết kế và vận hành log integrity

### 35.1. Nguồn và luồng ingest

- [ ] Inventory nguồn HRIS/IAM/IdP/SSO/SCIM/PAM/target/CI và service identities.
- [ ] Mỗi nguồn có owner, event schema và mục đích nghiệp vụ.
- [ ] Phân biệt actor person, executor machine principal và target account.
- [ ] Event IDs, source stream, sequence/epoch và correlation IDs có semantics rõ.
- [ ] Có eventTime/receivedAt và time-sync/skew monitoring.
- [ ] Ingestion qua TLS/mTLS hoặc channel xác thực phù hợp.
- [ ] Buffer/retry/backpressure có thống kê mất/duplicate.
- [ ] Heartbeat/source silence được giám sát.
- [ ] Raw evidence giữ riêng, enrichment không ghi đè raw bytes.
- [ ] Không ghi secret/token/PII không cần thiết vào log.

### 35.2. Bảo vệ và kiểm chứng mật mã

- [ ] Hash/MAC/signature và mục tiêu chống sửa được định nghĩa theo threat model.
- [ ] Canonicalization/framing/algorithm/version được tài liệu hóa.
- [ ] Sequence/hash chain hoặc batch commitments bảo vệ ordering theo stream.
- [ ] External checkpoint/anchor không nằm dưới toàn quyền writer.
- [ ] Signing/HMAC keys được quản lý KMS/HSM/vault với least privilege.
- [ ] Có key ID/rotation/compromise process và khả năng verify lịch sử.
- [ ] Archive có retention/immutability phù hợp và tách quyền admin.
- [ ] Verification được chạy định kỳ và khi điều tra, không auto-pass khi lỗi.
- [ ] Gaps/mismatches có triage, owner, severity và evidence preservation.
- [ ] Đã test tampering/replay/deletion/truncation ngoài các happy paths.

### 35.3. IAM lifecycle và kiểm toán

- [ ] Joiner logs nối identity proofing, account creation, baseline entitlements.
- [ ] Mover logs gồm remove role cũ, grant role mới và target readback.
- [ ] Leaver logs phân biệt disable request, target result, token/session closure.
- [ ] SoD/approval/exception logs có người duyệt độc lập và policy version.
- [ ] PAM/emergency logs có activation, session, credential và post-use review.
- [ ] OAuth/SCIM logs không rò credential và có client/target references.
- [ ] Service owner Mover/Leaver không làm mất workload audit ownership.
- [ ] Key/retention/log policy changes được audit độc lập.
- [ ] Access-to-logs được RBAC/ABAC, MFA/PAM theo risk và ghi lại.
- [ ] Retention/legal hold/privacy tuân thủ chính sách và có evidence.
- [ ] Dashboard không gọi “100% verified” khi target access còn bất đồng.
- [ ] Chỉ đóng incident/log-integrity remediation khi scope và trust đã được xác minh.

## 36. Bài tập tự kiểm tra

### 36.1. Bài A — Hash nằm cạnh log

Admin có quyền sửa `audit.log` và `audit.sha256`. Khi họ thay một event, hệ thống tính lại SHA-256 và vẫn PASS. Hãy giải thích tại sao, đề xuất signature/HMAC/anchor tách biệt và quyền lưu trữ phù hợp.

### 36.2. Bài B — Signed log có sự kiện sai

IdP ký event `ACCOUNT_DISABLED`, nhưng target SaaS vẫn cho Lan đăng nhập bằng local password. Log có integrity không? Quy trình JML cần thêm những evidence nào để kết luận offboarding đúng?

### 36.3. Bài C — Mất sequence 203

Collector nhận sequence 201, 202, 204. Liệt kê những nguyên nhân hợp lệ và độc hại có thể gây gap. Thiết kế kiểm heartbeat, retry, epoch, checkpoint và reconciliation.

### 36.4. Bài D — Timestamp lệch

HRIS ghi Leaver lúc 10:00; SIEM hiển thị log lúc 09:57 vì source clock chậm. Nên lưu `eventTime` và `receivedAt` thế nào, dùng trusted time/sequence ra sao để không kết luận sai SLA?

### 36.5. Bài E — Đổi signing key

Signing key V1 hết hạn và V2 được đưa vào sử dụng. Hệ thống cần lưu key ID, trust material và checkpoint chuyển epoch gì để kiểm chứng logs V1 trong 3 năm tới?

### 36.6. Bài F — PAM recording

Một phiên break-glass được quay video nhưng operator có thể xóa recording trước khi auditor xem. Hãy thiết kế custody, digest/anchor, external archive và actor attribution để cải thiện bằng chứng.

### 36.7. Bài G — Retention và xóa hợp lệ

Một stream đã hết thời gian lưu và không có legal hold. Xóa nó có phải log tampering không? Những approval, manifest, checkpoint và deletion audit nào phân biệt deletion đúng quy trình với xóa lén?

### 36.8. Bài H — Log collector offline

Collector offline 25 phút, producer có buffer 10 phút và không ghi drop count. Tổ chức có thể chứng minh completeness không? Hãy đề xuất buffering, heartbeat, reconciliation và incident reporting.

### 36.9. Bài I — Shared service account

Ba CI jobs cùng dùng OAuth client `deploy-prod`; mọi logs đều ghi chung một client ID. Hash/signature có đủ để quy trách nhiệm riêng từng job không? Gợi ý workload identities riêng và job IDs được ràng buộc với runtime đáng tin.

### 36.10. Bài J — Compromised signer

Private signing key bị lộ lúc 15:00 nhưng hệ thống chỉ phát hiện hôm sau. Những logs trước/sau thời điểm này còn độ tin cậy nào? External anchors và cross-source evidence giúp hạn chế vùng nghi vấn ra sao?

### 36.11. Bài K — Merkle inclusion

Auditor có Merkle proof chứng minh event #512 thuộc batch đã ký, nhưng nghi có 50 events bị loại trước khi lập tree. Inclusion proof có giải quyết completeness không? Cần thêm những controls nào?

### 36.12. Bài L — SoD quản trị log

Một admin có quyền cấp GlobalAdmin, thay log filter, xóa object archive và tự xác nhận verifier PASS. Xác định các xung đột SoD và đề xuất tách role, JIT/PAM, independent verification.

### 36.13. Bài M — OAuth credential leak

Client secret lộ trong log token endpoint được ký/đưa vào WORM. Tại sao integrity tốt chưa chắc an toàn? Hãy nêu kế hoạch redact future logs, revoke/rotate credential, xử lý archive access và điều tra secret exposure.

### 36.14. Bài N — Sửa sai event theo append-only

Một event `REVOCATION_VERIFIED_CLOSED` được phát sớm, sau đó phát hiện token còn hiệu lực. Có nên xóa/sửa event gốc? Hãy đề xuất correction/retraction event và remediation record giữ lịch sử minh bạch.

### 36.15. Bài O — Dashboard 100%

Báo cáo có “100% log signatures valid”, nhưng 20% service accounts chưa có owner, một HRIS feed im lặng 4 giờ và 12 Leaver accounts còn active tại SaaS. Vì sao không thể kết luận IAM audit đầy đủ? Xây dashboard phân biệt **integrity, completeness, correctness và effective-access closure**.

**Điểm cần ghi nhớ:** **Log integrity** trong IAM là khả năng bảo vệ hoặc **phát hiện việc sửa/xóa/chèn/đảo/replay dấu vết truy cập** trong một **trust model rõ ràng**. Hash chỉ là một mảnh ghép; cần **canonicalization, sequencing, hash-chain/MAC/chữ ký hoặc Merkle proof khi phù hợp, external anchors, key governance, immutable archive, independent verification và SoD**. Đồng thời phải bảo vệ **tính đầy đủ và tính đúng của evidence** bằng heartbeat, detection gaps và đối soát **HRIS, IdP/SSO, SCIM, RBAC/ABAC, PAM, machine identities và target actual permissions**. Trong vòng đời **Joiner–Mover–Leaver**, một log `REVOKE_REQUESTED` có integrity cao vẫn **không chứng minh quyền đã mất**; chỉ kết luận hoàn tất khi **target readback, session/token state, quyền hiệu lực và chuỗi audit có kiểm chứng** cùng phù hợp chính sách.

