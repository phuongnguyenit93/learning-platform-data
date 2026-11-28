# Policy review: rà soát chính sách mật mã và quản lý khóa

## 1. Chính sách tốt hôm nay có thể không còn phù hợp ngày mai

Một công ty triển khai **AES-256-GCM** để mã hóa hóa đơn, **TLS 1.3** cho các dịch vụ Java và **KEK** đặt trong KMS. Quy định nội bộ được phê duyệt từ một năm trước, yêu cầu mỗi khóa có owner, custodian và kế hoạch rotation. Tuy nhiên, qua thời gian:

- Một microservice mới được thêm quyền **KMS Decrypt** trên toàn bộ khóa của môi trường production.
- Đội vận hành chuyển một cặp private signing key sang keystore trong container mà không cập nhật key inventory.
- Một hệ thống legacy được miễn yêu cầu TLS mới trong ba tháng, nhưng ngoại lệ tồn tại mãi.
- Key đã quá kỳ xem xét vẫn được sử dụng để tạo ciphertext mới.
- Backup tồn tại nhiều năm, còn phiên bản KEK cũ đã lên lịch xóa.
- Một bản cập nhật thư viện/threat model làm thay đổi lựa chọn thuật toán cần được phê duyệt.
- Thông số KDF hoặc AEAD của ứng dụng thực tế không còn khớp hồ sơ chính sách.

**Policy review (rà soát chính sách)** là hoạt động đánh giá **mức độ phù hợp, tính hiệu lực và mức độ được thực thi** của cryptographic policy, từ văn bản đến các khóa, hệ thống, quyền truy cập và bằng chứng vận hành thực tế.

Một buổi review đúng nghĩa không chỉ hỏi: “Tài liệu này đã được ký chưa?” mà còn hỏi:

> Chính sách hiện tại có bảo vệ đúng tài sản và rủi ro không? Các kiểm soát được áp dụng ở đâu? Những gì chúng ta đo được có khớp điều đã phê duyệt không? Nếu không, ai chịu trách nhiệm sửa, khi nào và bằng chứng đóng việc là gì?

Trong phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chính sách cần bao phủ vòng đời từ sinh, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy khóa; đồng thời kết nối **mã hóa đối xứng/bất đối xứng, chữ ký số, KDF, KMS/HSM, envelope encryption, IAM và audit**. Review phải kiểm tra toàn bộ các mối nối đó, không chỉ tên thuật toán.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **policy review**, **key inventory reconciliation**, **technical configuration audit**, **cryptographic assessment** và **incident response**.
2. Xây dựng chương trình review dựa trên **độ rủi ro, chu kỳ, thay đổi lớn và tín hiệu cảnh báo**.
3. Xác định vai trò **policy owner, risk owner, key owner, custodian, application owner, reviewer độc lập và approver**.
4. Chuẩn bị evidence từ **inventory, KMS/HSM, IAM, TLS/PKI, source/config, CI/CD, audit và restore tests** mà không lộ bí mật.
5. Rà soát **algorithm profiles, key purposes, cryptoperiod, rotation, revocation, backup và destruction**.
6. Đánh giá các ngoại lệ, thuật toán legacy và yêu cầu **crypto-agility**.
7. Ghi nhận **findings, severity, remediation owners, deadlines, compensating controls và closure evidence**.
8. Triển khai ví dụ Java 17 để tự động phát hiện một số trường hợp **policy drift**.
9. Thiết kế checklist, negative tests và mẫu review packet có thể tái sử dụng.
10. Hiểu vì sao một review được ký duyệt **không đồng nghĩa đã chứng minh hệ thống bảo mật tuyệt đối**.

## 2. Định nghĩa và những việc policy review không phải

**Cryptographic policy** diễn đạt các quy định đã được phê duyệt: loại thuật toán nào dùng cho use case nào, ai được tạo/sử dụng khóa, khóa phải lưu ở đâu, thời hạn và phương án khôi phục ra sao.

**Policy review** kiểm tra **chính những quy định đó** có còn hợp lý và có được thực thi không. Nó có thể dẫn đến thay chính sách, thay cấu hình kỹ thuật hoặc khắc phục sai lệch mà **không nhất thiết phải thay toàn bộ văn bản**.

| Hoạt động | Đối tượng chính | Câu hỏi đặc trưng |
| --- | --- | --- |
| **Policy review** | Yêu cầu, phạm vi, rủi ro và hiệu lực của chính sách | Chính sách có còn phù hợp; các kiểm soát và bằng chứng có đáp ứng? |
| **Technical configuration audit** | Cấu hình thực tế của KMS/IAM/TLS/ứng dụng | Các thông số hiện có có khác baseline được duyệt không? |
| **Key inventory reconciliation** | Danh mục khóa so với khóa thực tế | Có key thiếu owner/version, key bị bỏ quên hay trạng thái sai không? |
| **Key usage review** | Quyền và hành vi Encrypt/Decrypt/Sign/Unwrap | Có principal dùng khóa sai mục đích hoặc quá rộng không? |
| **Cryptographic assessment** | Thiết kế primitive/giao thức/threat model | Cơ chế đã chọn có chống được tấn công được đặt ra không? |
| **Penetration test** | Bề mặt tấn công của hệ thống | Có đường khai thác cụ thể không, trong phạm vi thử nghiệm? |
| **Incident response** | Sự cố đang hoặc đã xảy ra | Cần cô lập, điều tra và khôi phục cái gì ngay? |
| **Compliance attestation** | Bằng chứng tuân thủ một bộ yêu cầu xác định | Có đủ chứng cứ theo phạm vi/kỳ kiểm tra quy định không? |

Một review có thể dùng kết quả từ các hoạt động khác, nhưng **không thay thế** chúng. Đặc biệt, việc kiểm thử unit test thành công chưa kiểm tra hết **quyền KMS thật, nguồn trust, backup nhiều năm và phân quyền tenant**.

### 2.1. Ba lớp review phải đi cùng nhau

~~~text
LỚP 1 — Policy adequacy
   Yêu cầu đã phù hợp tài sản, threat model và nghĩa vụ chưa?
                      |
                      v
LỚP 2 — Implementation conformance
   Thiết kế, code, KMS/IAM/TLS và runbook có thực hiện yêu cầu?
                      |
                      v
LỚP 3 — Operational effectiveness
   Bằng chứng vận hành chứng minh kiểm soát có thực sự chạy?
   Có drift, exceptions, cảnh báo, restore failure, quyền dư thừa?
~~~

Một cryptographic policy có thể **đúng về mặt câu chữ** nhưng triển khai sai. Ngược lại, code hiện tại dùng thuật toán hợp lý nhưng **không có owner, cryptoperiod hay quy trình thu hồi**; đó vẫn là khoảng trống quản trị phải được review.

### 2.2. Policy review không tự tạo bảo mật

Buổi họp với chữ ký phê duyệt chỉ chứng minh một quyết định theo quy trình. Nó **không tự**:

- Chặn được service account gọi Decrypt ngoài phạm vi.
- Loại bỏ AES-GCM nonce reuse trong code.
- Giữ lại KEK cần cho backup cũ.
- Khôi phục dữ liệu khi private key bị hủy nhầm.
- Xác thực được public signing key của đối tác.
- Ngăn attacker từng lấy plaintext hoặc DEK.
- Đảm bảo hệ thống sẽ mãi tuân thủ sau đợt review.

Giá trị nằm ở **phát hiện, ra quyết định, thực thi khắc phục và xác minh độc lập**.

## 3. Khi nào phải review?

Nên kết hợp **review định kỳ** và **review dựa trên sự kiện**. Không có một số ngày cố định tối ưu cho mọi doanh nghiệp; chu kỳ cần dựa trên độ rủi ro, vòng đời khóa, yêu cầu tổ chức và tốc độ thay đổi hạ tầng.

### 3.1. Review định kỳ theo rủi ro

Một chương trình minh họa:

| Đối tượng | Mức độ nhạy cảm | Nhịp rà soát ví dụ | Lý do |
| --- | --- | --- | --- |
| Root KEK/HSM administrators, signing keys cấp cao | Rất cao | Hàng quý hoặc khi có thay đổi | Blast radius lớn, quyền có thể ảnh hưởng nhiều hệ thống |
| IAM grants, KMS decrypt/sign quyền nhạy cảm | Cao | Hàng tháng và sau thay đổi quyền | Quyền sai có thể gây lộ dữ liệu ngay |
| TLS/certificate/trust và cryptographic profiles | Cao | Định kỳ theo policy, kèm automated checks | Trust/phiên bản có thể drift khi deploy |
| Inventory owner/custodian, cryptoperiod | Trung bình–cao | Hàng quý hoặc theo lifecycle | Tránh khóa vô chủ, quá hạn, backup thiếu |
| Tổng thể cryptographic policy | Tổ chức | Ít nhất theo lịch do chính sách quy định | Đánh giá threat model, yêu cầu mới và hiệu lực |
| Exceptions và kế hoạch migration | Theo mức rủi ro | Trước hạn hết hiệu lực và theo milestones | Tránh ngoại lệ trở thành vĩnh viễn |

**Đây chỉ là ví dụ thiết kế lịch**, không phải tuyên bố bắt buộc từ một chuẩn bên ngoài. Có thể review hàng ngày qua automation với một số control, nhưng **quyết định thay policy** vẫn cần thẩm quyền và phân tích.

### 3.2. Trigger review ngay khi có sự kiện đáng kể

- **Phát hiện lộ khóa, key usage compromise hoặc policy/grant compromise**.
- Thay **KMS provider, HSM partition, keystore, TLS termination layer, key custody**.
- Sự cố **certificate/trust chain**, signing key bị thu hồi, CA hoặc JWKS bị thay.
- Dịch vụ mới đưa **dữ liệu nhạy cảm hoặc tenant mới** vào phạm vi một KEK.
- Thay **thuật toán/giao thức, KDF parameters, key size, key schedule**.
- Có lỗ hổng đáng kể trong **thư viện mật mã/JDK/provider** hoặc thay đổi threat model.
- Mở **region/site mới**, điều chỉnh backup/retention, chuyển nhà cung cấp.
- Thay đổi nghĩa vụ pháp lý/contractual hoặc yêu cầu audit áp dụng.
- **Restore test thất bại**, khóa bị xóa nhầm, không giải được dữ liệu cũ.
- Xuất hiện **legacy exception quá hạn**, drift nghiêm trọng hoặc quyền Decrypt/Sign bất thường.
- Kế hoạch migration sang một profile mật mã hoặc cơ chế hậu lượng tử/hybrid được phê duyệt.

### 3.3. Review khi có sự cố không thay incident response

Nếu một principal đang lạm dụng KMS Decrypt, tổ chức phải **cô lập và ứng phó sự cố ngay** theo runbook. Không chờ phiên họp policy review quý sau. Policy review sau đó đánh giá **vì sao nguyên tắc cấp quyền, giám sát hoặc audit đã không đủ**, và thay policy/controls khi cần.

## 4. Ai review? Trách nhiệm và sự độc lập

Một review không hiệu quả nếu một người tự cấp quyền, tự xác nhận đúng và tự đóng tất cả findings.

| Vai trò | Công việc trong review | Ranh giới trách nhiệm |
| --- | --- | --- |
| **Policy owner / security governance** | Định nghĩa phạm vi, baseline, quy tắc và lịch review | Không mặc nhiên đọc raw keys/dữ liệu |
| **Risk owner** | Chấp nhận rủi ro còn lại, phê duyệt ngoại lệ theo thẩm quyền | Không biến ngoại lệ thành quyền tự ý bypass |
| **Key owner** | Chứng minh purpose, data classification, cryptoperiod, dependency và business impact | Không tự quyết mọi thao tác hủy mà bỏ kiểm tra recovery |
| **Key custodian** | Cung cấp evidence custody, key states, grants, backup, restore và ceremony | Không mặc nhiên có quyền Decrypt hoặc Sign |
| **Application owner** | Giải thích code paths, AAD, nonce, user/tenant authorization, library/provider | Không tự cấp KMS quyền rộng hơn chính sách |
| **KMS/HSM/IAM administrator** | Xuất metadata/read-only evidence, sửa grant/state theo change được duyệt | Không nên là approver duy nhất cho thao tác của chính mình |
| **SRE/platform** | Cung cấp TLS, runtime, audit, backup, monitoring và sự kiện deploy | Không làm lộ session keys qua debug để chứng minh hệ thống hoạt động |
| **Independent reviewer / auditor** | Đối chiếu evidence với baseline, thách thức giả định và xác minh closure | Không cần raw secret hoặc quyền thao tác khóa |
| **Change approver** | Phê duyệt policy change/exception/remediation có rủi ro | Phải độc lập tương xứng độ nhạy của thay đổi |

### 4.1. RACI minh họa

Trong RACI: **R** = thực hiện, **A** = chịu trách nhiệm cuối cùng, **C** = tham vấn, **I** = nhận thông tin. Ví dụ:

| Hoạt động | Security policy owner | Key owner | Custodian | App/platform owner | Independent reviewer |
| --- | --- | --- | --- | --- | --- |
| Cập nhật cryptographic profile | A | C | C | R/C | C |
| Đối soát key inventory/KMS | C | A | R | C | R kiểm tra |
| Rà soát IAM grants/usage | A/C | C | R | R | R kiểm tra |
| Review data-at-rest/TLS implementation | A/C | C | C | R | R kiểm tra |
| Phê duyệt ngoại lệ rủi ro cao | A hoặc risk approver được ủy quyền | C | I | R đề xuất | C |
| Thực thi rotation/recovery | C | A | R | R khi liên quan | I hoặc witness |
| Xác minh đóng finding | A/C | C | R nếu được giao sửa | R nếu được giao sửa | R xác minh độc lập |

Bảng chỉ là gợi ý. Trong tổ chức thực, phải xác định **một đầu mối accountable cuối cùng cho từng quyết định**, thẩm quyền phê duyệt và mức độ kiểm tra chéo theo phân loại khóa.

### 4.2. Nguồn evidence và người chấm phải phân tách

Nếu một kỹ sư khẳng định **“mọi KEK đều non-exportable”**, reviewer nên đối chiếu:

- **Key attributes** thực tế trong KMS/HSM.
- **Key policy/grants** có cho phép thao tác nguy hiểm không.
- **Đường import/export/backup** có tồn tại không.
- **Audit use** cho biết các key có được dùng đúng purpose không.
- **Runbook** có xử lý được việc mất credential hoặc failover không.

Một screenshot đơn lẻ từ console có thể cũ hoặc không đại diện mọi region. Cần **thời điểm, môi trường, key ID, source và người thu thập** cho evidence.

## 5. Bước 1 — Xác định phạm vi review và baseline có thẩm quyền

Trước khi đọc dữ liệu thực tế, xác định **baseline policy version** đang áp dụng. Nếu một môi trường dùng bản 2 nhưng reviewer so với bản 4 chưa hiệu lực, findings sẽ sai.

### 5.1. Scope bắt buộc rõ ràng

Một review packet nên ghi:

- **Review ID** và review window.
- **Module/service/environment** và nơi đặt dữ liệu.
- **Các hệ thống/trust boundaries** trong phạm vi.
- **Data classification** và thời hạn giữ bí mật dữ liệu.
- **Key classes**: DEK, KEK, root, signing, HMAC, ephemeral, PSK, derived key.
- **Key providers**: KMS, HSM, software keystore, cloud service.
- **Policy/profile version** có hiệu lực và ngày áp dụng.
- **Các ngoại lệ hợp lệ** cùng giới hạn thời gian.
- **Nguồn evidence** và thời điểm chụp snapshot.
- **Tiêu chí pass/fail, mức độ rủi ro và cơ chế escalation**.
- **Người review, người được review và người phê duyệt**.

### 5.2. Không tự đoán khi thiếu dữ liệu

Ví dụ key inventory báo **ACTIVE**, nhưng API KMS hiện tại báo **DISABLED**. Đây là **discrepancy phải điều tra**. Không tự sửa inventory rồi xóa dấu vết để bảng thống kê “khớp”.

Khi thiếu log/snapshot, nên ghi **NOT_EVALUATED hoặc INSUFFICIENT_EVIDENCE**, không đánh dấu PASS vì không tìm thấy sai phạm.

### 5.3. Phân loại kết quả kiểm tra

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| **PASS** | Có đủ evidence để xác nhận đạt yêu cầu trong phạm vi | Lưu liên kết evidence và thời điểm |
| **FAIL** | Evidence cho thấy không đạt baseline | Tạo finding/remediation |
| **PARTIAL** | Một phần phạm vi đạt, phần khác chưa đạt | Tách scope và đánh giá rủi ro còn lại |
| **NOT_APPLICABLE** | Control thực sự không liên quan | Ghi lý do rõ, có thể được xác minh |
| **NOT_EVALUATED** | Chưa kiểm tra | Bổ sung review trước sign-off nếu bắt buộc |
| **INSUFFICIENT_EVIDENCE** | Thiếu/chưa tin được bằng chứng | Yêu cầu evidence mới; không mặc nhiên PASS |
| **EXCEPTION_APPROVED** | Có ngoại lệ có hiệu lực đúng phạm vi | Kiểm tra expiry và compensating controls |

**Một exception hợp lệ không biến hành vi yếu thành an toàn về mặt mật mã**; nó chỉ là quyết định quản trị rủi ro có phạm vi và thời hạn.

## 6. Bước 2 — Thu thập evidence mà không xuất khóa bí mật

Tổ chức phải chứng minh trạng thái thực tế nhưng tránh việc “kiểm tra bảo mật” lại làm lộ private key, DEK hoặc password.

### 6.1. Evidence matrix

| Control cần review | Nguồn evidence phù hợp | Những gì không cần thu thập |
| --- | --- | --- |
| Key ownership/custodian | Inventory và HR/role mapping đáng tin | Raw key, mật khẩu của custodian |
| KMS key state/type/attributes | KMS/HSM describe/list metadata có giới hạn | Plaintext KEK/DEK |
| IAM least privilege | Effective permissions, grants, key policy, service account | Access token sử dụng được |
| Crypto algorithm/config | Source/config review, SBOM, JDK/provider settings, CI tests | Dữ liệu production rõ |
| AEAD nonce/AAD | Design, code, tests, usage metrics, sample package giả lập | DEK hoặc dữ liệu người dùng thật |
| Certificate/trust | Cert metadata, trust store entries, TLS test evidence | Private signing key |
| Signature/HMAC use | Key references, code/config, policy, test vectors giả | HMAC secret/private signing key |
| Rotation/cryptoperiod | Key version, timestamps, change approvals, migration status | Dữ liệu/khóa dạng rõ |
| Backup/restore | Restore report, version references, test result | Recovery shares dưới dạng rõ |
| Key usage/audit | KMS/HSM event metadata, anomaly alerts | Payload nhạy cảm, traffic secrets |
| Exception/risk acceptance | Signed approval, scope, expiry, mitigation status | Secret để tái tạo sự cố |

### 6.2. Tính đáng tin cậy của evidence

Review phải kiểm tra:

1. **Nguồn**: API/tài khoản nào đã xuất evidence, có đủ quyền đọc để bao phủ phạm vi không?
2. **Thời điểm**: cấu hình tại lúc nào; có thay đổi sau đó không?
3. **Tính toàn vẹn**: bằng chứng có được bảo vệ khỏi sửa/xóa?
4. **Khả năng tái hiện**: có câu truy vấn/cấu hình/commit/ticket ID để chạy lại?
5. **Độ đầy đủ**: đã bao phủ mọi environment/region/account/partition/tenant chưa?
6. **Tính đúng mục tiêu**: đang kiểm tra production hay accidentally là staging?
7. **Sự độc lập**: chỉ dựa vào owner tự khai hay đã có dữ liệu quan sát khách quan?
8. **Minimization**: evidence có chứa thông tin cá nhân hoặc secret không cần thiết không?

Một **screenshot “AES-256 enabled”** không chứng minh code dùng **GCM với nonce không trùng**. Một **KMS key non-exportable** không chứng minh mọi principal đều bị chặn **Decrypt/Sign** quá rộng.

### 6.3. Mẫu evidence reference

~~~yaml
evidenceId: ev-kms-grants-2026-11
controlId: IAM-KMS-04
reviewId: crypto-review-prod-q4-example
collectedAt: "2026-11-28T02:00:00Z"
sourceType: KMS_EFFECTIVE_PERMISSIONS
sourceRef: "evidence-store://redacted/immutable-record-id"
environment: production
scope:
  service: billing
  account: production-account
  region: selected-region
collectedByRole: security-auditor
integrityVerification: signed-or-immutable-store-reference
containsRawKeyMaterial: false
retentionPolicyRef: audit-retention-profile
~~~

Đây là **mẫu mô tả evidence**, không phải schema bắt buộc của một công cụ. Không dùng chuỗi "integrityVerification" tự khai làm thay cơ chế chứng minh evidence có thật.

### 6.4. Luồng bằng chứng từ nguồn kỹ thuật đến quyết định

~~~mermaid
flowchart LR
    INV["Inventory + owner/custodian"] --> COLLECT["Read-only evidence collection"]
    KMS["KMS/HSM key attributes + usage"] --> COLLECT
    IAM["IAM grants + principal mapping"] --> COLLECT
    APP["Application, TLS, CI tests"] --> COLLECT
    REST["Backup/restore evidence"] --> COLLECT
    COLLECT --> VALIDATE["Kiểm tra source, scope, time, integrity"]
    VALIDATE --> COMPARE["So baseline policy + effective controls"]
    COMPARE --> RESULT{"Đủ và khớp evidence?"}
    RESULT -->|"Có"| PASS["PASS + evidence reference"]
    RESULT -->|"Sai lệch"| FIND["Finding + severity + owner"]
    RESULT -->|"Thiếu"| GAP["INSUFFICIENT_EVIDENCE"]
    FIND --> RETEST["Remediation + independent retest"]
    RETEST --> COMPARE
~~~

Điểm kiểm tra quyết định nằm ở bước **VALIDATE**: một snapshot sai environment hoặc thiếu quyền liệt kê key không thể được dùng để kết luận rằng không có key bất thường. Việc làm sạch evidence phải giữ lại **nguồn và giới hạn bao phủ**, không tự động biến dữ liệu thiếu thành PASS.

## 7. Bước 3 — Rà soát key inventory và trách nhiệm

### 7.1. Những câu hỏi cần trả lời

- Có **key ID/alias** tồn tại trong KMS/HSM mà không có bản ghi inventory không?
- Có bản ghi inventory trỏ tới khóa đã **destroyed** hoặc không còn tồn tại?
- **Owner/custodian** có còn thuộc nhóm, đúng quyền và có backup/escalation?
- Các key có **purpose, algorithm, key class, state, cryptoperiod, key version** không?
- Key được tạo/import qua **runbook/approval** nào?
- **Exportability** và key attributes có khớp policy, nhất là root/KEK/signing key?
- Có **default/root keys chia sẻ mọi tenant** mà chính sách yêu cầu tách không?
- Các **wrapped DEK, dữ liệu, backup và verifier** còn phụ thuộc key version nào?
- Có khóa **orphan** hay chỉ có một người duy nhất nắm recovery material không?
- Có key được gắn nhãn retired nhưng vẫn **Encrypt/Sign mới**?

### 7.2. Đối soát hai hướng

~~~text
KMS/HSM actual keys ──(join key ID/version)──> Approved key inventory
         |                                       |
  Actual nhưng không có inventory        Inventory nhưng không có actual
         |                                       |
     UNREGISTERED KEY                         STALE / LOST REFERENCE
         |
   Kiểm tra grant, state, purpose, owner, rotation, dependencies
~~~

Cần đối soát **cả actual → inventory** và **inventory → actual**. Chỉ đọc bảng inventory không tìm được các khóa tạo thủ công ngoài quy trình. Chỉ đọc KMS list không biết khóa đó bảo vệ dataset nào hoặc có owner được phê duyệt hay không.

### 7.3. Rà soát key owner, custodian và bàn giao

Một người rời công ty có thể không còn trong danh sách nhân sự nhưng vẫn có:

- IAM role kế thừa từ nhóm cũ.
- API token hoặc service account chia sẻ.
- HSM operator card hoặc quyền truy cập vật lý.
- Recovery share cất offline.
- Quyền thay KMS policy, trust anchor hoặc xóa log.

Policy review phải kiểm tra **trách nhiệm và quyền thực tế**, không chỉ tên ghi trong tài liệu.

## 8. Bước 4 — Rà soát thuật toán, primitive và giao thức

Review cần xem cả **độ phù hợp của chính sách** với threat model và **độ phù hợp của triển khai** với profile được duyệt.

### 8.1. Mã hóa dữ liệu at rest

| Control | Câu hỏi review | Evidence |
| --- | --- | --- |
| Approved AEAD | Dữ liệu mới dùng AES-GCM hoặc cơ chế đã duyệt đúng use case? | Code/config test, profile |
| Key generation | DEK được sinh đủ entropy qua CSPRNG/KMS? | Key-generation path, KMS API |
| Nonce uniqueness | Nonce có tránh trùng dưới cùng DEK kể cả multi-instance/restart? | Design + volume limits + tests |
| AAD binding | Tenant/object/purpose được xác thực, encoding nhất quán? | Code, test sai tenant/AAD |
| Tag verification | App fail-closed nếu tag sai? | Negative tests, code review |
| Envelope | DEK được wrap bởi KEK phù hợp, key ID/version đầy đủ? | Storage schema, KMS config |
| Replay/rollback | Bản mã hợp lệ cũ có thể thay dữ liệu hiện tại trái phép không? | Version/state controls |
| Backup/restore | Có đủ ciphertext + wrapped DEK + key dependencies? | Restore test |

**Không kết luận “PASS” chỉ vì có tên AES-256 trong cấu hình.** Nonce trùng hoặc thiếu kiểm tra tag có thể phá một thiết kế vốn dùng key mạnh.

### 8.2. TLS, PKI và key establishment

Review nên kiểm tra:

- **TLS profile** thực tế của client/server, protocol versions và groups.
- **Certificate chain, hostname/service identity validation**, trust anchors.
- **mTLS** khi chính sách yêu cầu hai phía xác thực.
- Cách **resumption PSK, PSK-only/PSK+DHE và 0-RTT** được cấu hình nếu sử dụng TLS 1.3.
- Việc cấm **TrustManager/HostnameVerifier bỏ xác thực**.
- Phương án **renewal, revocation, incident và trust rotation**.
- Không xuất **traffic secrets hoặc key logs** ở production trừ tình huống điều tra được phê duyệt.
- **Forward secrecy** có thực sự đạt theo chế độ key establishment, không chỉ theo tên phiên bản TLS.
- Business authorization sau khi kết nối đã được xác thực.

Lưu ý: **TLS 1.3 PSK-only** không có forward secrecy đối với việc PSK bị lộ về sau, và **0-RTT early data** có khác biệt về FS/replay. Review phải biết **nhánh handshake** khi đưa ra kết luận, không dùng một phép kiểm tra protocol string để khẳng định mọi bản tin đều có FS.

### 8.3. Chữ ký số và trust

- Private signing key có đúng **purpose/algorithm/key usage** không?
- Quyền **Sign** có thể bị workload sử dụng ký payload tùy ý không?
- Public verification key đến từ **PKI/JWKS/trust store đã xác thực** hay request không tin cậy?
- Khi Verify, ứng dụng còn kiểm tra **issuer, audience, expiry, tenant, operation và replay** chưa?
- Cách xử lý **rotate signing key, kid/key version, lưu lịch sử trust** đã có?
- Có hỗ trợ xác minh thông điệp cũ theo chính sách khi key đã retired không?
- Chữ ký hợp lệ có bị nhầm với **phân quyền nghiệp vụ** không?

### 8.4. Hash, HMAC, password KDF và HKDF

**Hash nhanh** như SHA-256 không tương đương chữ ký hoặc MAC. Review cần phân biệt:

- Digest có từ **nguồn tin cậy** hay attacker thay được cả file và digest?
- HMAC key có bị chia cho client chỉ để Verify không?
- Có tự chế MAC bằng SHA256(secret + message) không?
- Password verifier dùng **password-based KDF** với salt/cost/version phù hợp?
- Có đưa password trực tiếp, qua padding hoặc **SHA-256(password)** vào AES?
- HKDF có được dùng với IKM đủ mạnh và **domain separation** rõ?
- Salt, nonce, context, KDF params có được phiên bản hóa và có giới hạn tài nguyên?

### 8.5. Crypto-agility và lộ trình thuật toán mới

Policy review nên xem xét sự thay đổi của:

- Yêu cầu thời hạn bảo mật dữ liệu.
- Provider/JDK/library và các thuật toán được hỗ trợ.
- Tình trạng thuật toán legacy và kế hoạch migration.
- Những yêu cầu mới liên quan tới **key establishment/chữ ký hậu lượng tử hoặc hybrid** nếu threat model cần.

Đây là **đánh giá chiến lược**, không phải lý do để tự ghép ECDH/KEM/HKDF thành một giao thức không có chuẩn. Policy phải quy định **profile được thẩm định, khả năng tương tác và kế hoạch rollback/migration an toàn**.

## 9. Bước 5 — Rà soát key lifecycle, cryptoperiod và recovery

Review phải nhìn một key qua toàn bộ vòng đời, không chỉ ngày tạo.

### 9.1. Ma trận vòng đời

| Giai đoạn | Câu hỏi kiểm tra | Bằng chứng |
| --- | --- | --- |
| **Generate/Import** | Key material sinh từ CSPRNG/HSM đúng thuật toán, có approval? | Provider metadata, change ticket |
| **Register** | Có key ID/version, owner, custodian, purpose và inventory? | Inventory đối soát thực tế |
| **Distribute/Grant** | Principal nào được dùng key, cấp theo least privilege? | IAM grants/effective permissions |
| **Store** | KEK/private key ở ranh giới phù hợp, non-exportable khi yêu cầu? | KMS/HSM attributes, storage architecture |
| **Use** | Encrypt/Decrypt/Sign/Wrap đúng purpose/tenant/cryptoperiod? | Code/config, usage audit |
| **Rotate/Rekey** | Key mới có được dùng cho dữ liệu mới, key cũ xử lý thế nào? | Rotation log, key version |
| **Suspend/Revoke** | Có thể chặn nhanh key hoặc principal nguy hiểm? | Incident drill/change log |
| **Archive/Read old** | Có phase decrypt-only/verify-only nếu cần và policy cho phép? | State/usage enforcement |
| **Recover** | Backup có đủ dependencies và đã thử giải mã? | Restore test evidence |
| **Destroy** | Không còn dữ liệu cần key, có approval và xác nhận độc lập? | Dependency report, deletion evidence |

### 9.2. Không dùng cryptoperiod như một con số chung

Cryptoperiod phụ thuộc **loại khóa, thuật toán, mức độ sử dụng, lượng dữ liệu, dữ liệu cần giữ, nguy cơ lộ và yêu cầu chính sách**. Ví dụ:

- **Ephemeral session key:** sống trong phiên/giai đoạn ngắn.
- **Data-encryption key:** có thể sống qua nhiều bản ghi nhưng phải có giới hạn, nonce strategy và rotation.
- **KEK:** có thể tồn tại lâu hơn DEK để mở dữ liệu cũ.
- **Private signing key:** có thời hạn ký mới; chữ ký lịch sử có thể cần verification evidence.
- **HMAC key:** có cửa sổ phát hành MAC mới và cửa sổ xác minh old tags theo giao thức.
- **Password-derived key:** phụ thuộc password/KDF/recovery policy, không dùng lẫn với random DEK.

Review nên phát hiện **key quá hạn dùng cho operations mới** thay vì tùy tiện xóa tất cả khóa đã tới ngày rotate.

### 9.3. Rewrap khác re-encrypt

~~~text
Trước:
  plaintext --DEK-v1--> ciphertext-v1
  DEK-v1 --KEK-v1--> wrappedDEK-v1

Rewrap (đổi lớp bảo vệ):
  DEK-v1 --KEK-v2--> wrappedDEK-v2
  ciphertext-v1 có thể giữ nguyên.

Re-encrypt (đổi khóa dữ liệu):
  plaintext --DEK-v2 + nonce mới--> ciphertext-v2
  DEK-v2 --KEK được phép--> wrappedDEK-v2
~~~

Nếu **DEK đã bị lộ**, chỉ rewrap cùng DEK không phục hồi bí mật của dữ liệu cũ. Nếu **KEK bị lộ cùng wrapped DEKs lịch sử**, phải đánh giá phạm vi ảnh hưởng thực tế và liệu có cần re-encrypt bằng DEK mới.

### 9.4. Phải review khả năng khôi phục trước khi hủy khóa

Reviewer cần một **dependency graph**:

~~~mermaid
flowchart TD
    OLD["KEK-v1 sắp xóa"] --> W1["Wrapped DEKs vẫn dùng KEK-v1"]
    OLD --> BK["Backup và archive dùng version cũ"]
    W1 --> DB["Ciphertext cần đọc"]
    BK --> RESTORE["Quy trình restore lịch sử"]
    DB --> DEC{"Đã rewrap/re-encrypt và thử restore?"}
    RESTORE --> DEC
    DEC -->|"Chưa"| BLOCK["BLOCK deletion; tạo remediation"]
    DEC -->|"Rồi; đã có approval"| APPROVE["Có thể tiếp tục theo destroy runbook"]
~~~

Một backup **checksum khớp** nhưng thiếu KEK hoặc AAD/KMS context để unwrap vẫn có thể **không khôi phục được plaintext**. Review phải yêu cầu restore test phù hợp, không chỉ báo cáo backup thành công.

### 9.5. Key destruction không phải xóa row inventory

Khi key bị destroy, cần giữ **metadata/audit thích hợp** theo retention để biết:

- Key từng tồn tại và bảo vệ dữ liệu nào.
- Ai phê duyệt và thực thi hủy.
- Dữ liệu/bản sao nào đã hoàn tất migration hoặc tiêu hủy.
- Recovery materials có còn bản sao nguy hiểm không.
- Những hệ thống cũ có thể vẫn gọi key ID đã hủy không.

Không giữ raw key chỉ vì muốn “giữ bằng chứng audit”.

## 10. Bước 6 — Rà soát IAM/KMS/HSM và quyền dùng khóa

Một key non-exportable **có thể vẫn bị lạm dụng qua API**. Review phải phân biệt quyền biết key material với quyền yêu cầu KMS thực hiện thao tác.

### 10.1. Ma trận kiểm tra quyền

| Role/workload | Key operation được mong đợi | Rủi ro nếu được cấp thêm |
| --- | --- | --- |
| **Billing writer** | GenerateDataKey/Encrypt trong tenant được phép | Decrypt mọi tenant làm lộ lịch sử dữ liệu |
| **Billing reader** | Unwrap/Decrypt đúng resource | Sign hoặc thay key policy không cần thiết |
| **Release signer** | Sign đúng signing key/purpose | Quyền ký token hoặc chứng từ khác nếu không tách mục đích |
| **Key custodian** | Quản lý custody/rotation/backup theo approval | Decrypt/Sign mặc định không cần thiết |
| **KMS key administrator** | Key policy/grant có SoD và audit | Tự tạo quyền Decrypt hoặc xóa log |
| **Security auditor** | Read-only metadata và audit evidence | Raw key export hoặc thay policy |
| **Recovery operator** | Quyền break-glass có thời hạn/quorum | Quyền khẩn cấp tồn tại vô hạn |

### 10.2. Đánh giá effective permissions

Không chỉ xem những policy trực tiếp gán vào role. Cần xét:

- **Group membership, inherited roles, trust relationships**.
- Grants tạm thời đã hết hạn nhưng chưa thu hồi.
- Service accounts chia sẻ.
- Key policy/resource policy và identity policy cùng tác động.
- Cross-account/region permissions và điều kiện theo environment.
- Quyền **Sign, Decrypt, Unwrap, DeriveKey, Export, ScheduleDeletion**.
- Quyền tạo grant mới hoặc sửa trust store.
- Khả năng truy cập backup/recovery vault ngoài KMS.

Nếu một tài khoản không thể export private signing key nhưng có quyền **Sign không giới hạn**, attacker vẫn có thể tạo chữ ký giả thông qua HSM.

### 10.3. KMS encryption context không phải quyền tenant đầy đủ

Một số KMS hỗ trợ **encryption context** hoặc AAD khi wrap/unwrap. Review phải xác minh:

1. Context có được ràng buộc vào thao tác không?
2. Context khi Decrypt có được dựng từ **nguồn đáng tin** không?
3. IAM/key grants có hạn chế principal và key IDs tương ứng không?
4. Ứng dụng có kiểm tra **business authorization trên tenant/record** không?
5. AAD của bản mã dữ liệu có được xây dựng riêng và xác thực không?

**KMS context ≠ data AAD ≠ business authorization.** Chúng có thể bổ trợ nhau nhưng không tự thay thế.

### 10.4. Kiểm tra hiệu lực khi revoke

Hãy đặt câu hỏi: khi một principal bị khóa hoặc key bị disable, **đường dữ liệu nào vẫn còn khả năng dùng secret cũ?**

- Plaintext DEK đã được cache trong RAM?
- Token IAM còn sống trong một phiên?
- Một worker có bản sao private signing key cũ?
- Backup có KEK dưới quyền account khác?
- Một deployment bị bỏ quên có credential chia sẻ?

**Revoke API grant không làm attacker quên raw key đã sao chép.** Review cần hiểu cache, session expiry và phạm vi phụ thuộc.

## 11. Bước 7 — Review ngoại lệ và legacy migration

Một exception là **quyết định chấp nhận rủi ro có kiểm soát**, không phải phép màu khiến một thuật toán yếu trở thành mạnh.

### 11.1. Bản ghi ngoại lệ tối thiểu

~~~yaml
exceptionId: crypto-exception-legacy-import-example
requestedByTeam: legacy-integration
riskOwnerRole: integration-risk-owner
controlId: CRYPTO-ALGORITHM-03
environment: production
scope:
  direction: decrypt-only
  dataset: historical-invoices
  allowNewEncryption: false
reason: legacy-ciphertext-migration
compensatingControls:
  - isolated-worker-with-restricted-access
  - protected-input-and-output
  - strict-audit-and-rate-limits
approvedFrom: "2026-10-01"
expiresAt: "2027-01-31"
migrationMilestoneRef: change/legacy-migration
approvalEvidenceRef: approval/legacy-exception
status: ACTIVE
~~~

Mẫu này không phải cấu hình máy thực thi và không tự thay quy trình risk acceptance.

### 11.2. Kiểm tra exception theo bốn câu hỏi

1. **Đúng phạm vi không?** Chỉ dataset/tenant/service cần ngoại lệ hay toàn hệ thống?
2. **Còn hiệu lực không?** Có expiration và approver đúng thẩm quyền?
3. **Compensating controls có chạy không?** Không chỉ liệt kê trong ticket.
4. **Migration có tiến triển không?** Có milestone, owner, dữ liệu còn lại và deadline?

Nếu exception đã hết hạn, policy review phải đánh dấu **FAIL/EXPIRED** và thực hiện quy trình khắc phục; **không tự kéo dài** bằng cách cập nhật ngày hết hạn mà không approval.

### 11.3. Decrypt-only khác downgrade/fallback

Việc đọc ciphertext legacy có phiên bản và phạm vi đã được phê duyệt để **re-encrypt sang profile mới** có thể là một bước migration. Nhưng tuyệt đối không xử lý:

~~~text
AES-GCM authentication failure
    -> bỏ tag
    -> thử ECB/CBC
    -> trả plaintext nếu thấy có vẻ đọc được
~~~

Tag failure phải **fail closed**. Migration cần **format/version và nguồn dữ liệu được xác định trước**, không cho attacker ép đường legacy qua một lỗi giải mã hiện tại.

### 11.4. Chính sách mới cũng cần lộ trình tương thích

Khi policy không còn cho phép một kiểu key/cipher:

- Ngừng **tạo bản mã hoặc chữ ký mới** theo thuật toán cũ ở mốc đã phê duyệt.
- Cho phép đọc/xác minh lịch sử trong phạm vi được phân tích nếu cần.
- Theo dõi số bản ghi còn phụ thuộc thuật toán/key version cũ.
- Chuẩn bị data migration và backup/restore phù hợp.
- Cập nhật clients/trust stores/signature verifiers.
- Đưa điều kiện **loại bỏ legacy** thành một chỉ tiêu có người chịu trách nhiệm.

## 12. Bước 8 — Xác minh kiểm soát bằng test và giám sát

### 12.1. Positive và negative tests

Các tests phải chứng minh **đường từ chối** hoạt động, không chỉ một lệnh Encrypt/Decrypt thành công.

| Test case | Kỳ vọng |
| --- | --- |
| Writer tenant A dùng key ACTIVE hợp lệ của tenant A | ALLOW |
| Reader tenant B xin giải mã ciphertext tenant A | DENY |
| Key LEGACY_READ_ONLY dùng tạo bản mã mới | DENY |
| Key LEGACY_READ_ONLY dùng đọc dữ liệu cũ có quyền | ALLOW có điều kiện |
| Ciphertext/tag/AAD bị sửa | AUTHENTICATION FAILURE |
| Nonce generator bị reset khiến có thể reuse | TEST/CONTROL FAIL |
| KMS principal thiếu quyền Decrypt/Unwrap | DENY từ KMS |
| Private signing key bị gọi ngoài purpose | DENY qua policy/service guardrail |
| JWT/webhook dùng public key chưa được tin | DENY trust |
| TLS certificate sai hostname hoặc chain | DENY connection |
| TLS provider tắt certificate validation | CONFIGURATION FINDING |
| KDF password có cost/format sai profile | DENY hoặc MIGRATION theo policy |
| Exception legacy đã hết hạn | DENY tác vụ mới / REVIEW FINDING |
| Xóa KEK khi backup cũ còn phụ thuộc | BLOCK deletion |
| KMS key đã disable nhưng app giữ DEK cache lâu | REVOKE/CACHE CONTROL FINDING |
| Restore backup không đủ wrapped DEK/context | RESTORE TEST FAIL |

### 12.2. Static, integration và runtime testing

- **Static scan/source review:** tìm AES/ECB, TrustManager vô hiệu hóa kiểm tra, hard-coded keys, raw password-to-AES, crypto tự chế.
- **Unit tests:** kiểm tra role–tenant–key–purpose–state, nonce/AAD, error handling.
- **Integration tests:** đánh giá effective IAM/KMS grants và provider behavior trong môi trường thử.
- **TLS tests:** kiểm tra protocol, certificate trust/hostname/mTLS và chính sách resumption.
- **Recovery tests:** giải mã thực tế từ backup giả lập hoặc bản test có cùng workflow.
- **Runtime drift:** so sánh policy version, deployed configuration và grants hiện tại.
- **Audit sampling:** đối chiếu request IDs với key usage events và change approvals.

Không dùng **production plaintext/private keys** làm test vectors. Không bật TLS key logging ở production chỉ để minh chứng dễ dàng.

### 12.3. Lấy mẫu không thay bao phủ toàn diện

Có thể **tự động kiểm 100% inventory metadata và key states**, nhưng việc xem xét code/threat model hoặc proof of business authorization có thể cần lấy mẫu theo rủi ro.

Nên ghi rõ:

- **Population**: toàn bộ đối tượng thuộc phạm vi.
- **Sample size** và cách chọn: random, stratified, high-risk, recent changes.
- **Coverage**: region, tenant, key type, owner, môi trường.
- **Selection rationale**: tại sao mẫu đại diện cho rủi ro cần đánh giá.
- **Limitations**: kết quả không tự suy ra mọi bản ghi chưa được thử.

Nếu mẫu phát hiện **lỗi nghiêm trọng**, cần mở rộng phạm vi thay vì dùng tỷ lệ PASS của mẫu còn lại để bỏ qua.
## 13. Bước 9 — Ghi nhận findings, đánh giá rủi ro và ưu tiên khắc phục

Một review không hoàn thành khi chỉ tạo danh sách “đúng/sai”. Mỗi sai lệch cần **quyền sở hữu, mức độ nghiêm trọng, phạm vi dữ liệu, hành động sửa và bằng chứng xác minh**.

### 13.1. Một finding phải có thông tin gì?

| Trường | Mục đích |
| --- | --- |
| **findingId / controlId** | Liên kết sai lệch với điều khoản chính sách |
| **reviewId / policyVersion** | Cho biết đánh giá theo baseline nào |
| **asset/key ID/version** | Định vị khóa hoặc dịch vụ bị ảnh hưởng |
| **actual vs expected** | Chỉ ra trạng thái quan sát và yêu cầu tương ứng |
| **evidenceRefs** | Bằng chứng có nguồn, thời điểm, độ tin cậy |
| **severity / impact** | Mức rủi ro và phạm vi ảnh hưởng |
| **findingOwner / riskOwner** | Ai sửa và ai chấp nhận rủi ro |
| **dueAt** | Hạn xử lý theo chính sách mức rủi ro |
| **compensatingControls** | Kiểm soát tạm thời nếu chưa khắc phục ngay |
| **remediationPlan** | Những bước thay cấu hình, khóa, quyền hoặc code |
| **retestEvidence / verifiedBy** | Bằng chứng đóng vấn đề và người kiểm tra độc lập |
| **status** | OPEN, IN_PROGRESS, MITIGATED, RESOLVED, ACCEPTED_RISK... |

**Không ghi root secret, private key, DEK rõ hoặc password** trong finding/ticket để “đưa bằng chứng”. Có thể dẫn tới bản ghi audit được bảo vệ theo quyền truy cập.

### 13.2. Severity dựa trên rủi ro, không chỉ loại thuật toán

Ví dụ định tính:

| Mức minh họa | Tình huống điển hình | Hướng xử lý |
| --- | --- | --- |
| **CRITICAL** | Khóa cấp cao/tenant-wide có nguy cơ lộ đang diễn ra; bypass xác thực cho hệ thống rất nhạy cảm | Escalate, kích hoạt incident response và giảm thiểu ngay |
| **HIGH** | Quyền KMS Decrypt rộng, nonce reuse tiềm năng, không có recovery cho backup quan trọng | Ưu tiên cao, giới hạn quyền/tác động, xác minh sớm |
| **MEDIUM** | Rotation/review quá hạn có phụ thuộc được kiểm soát; thiếu metadata quan trọng | Tạo remediation có hạn, bổ sung evidence |
| **LOW** | Lỗi ghi nhãn không ảnh hưởng sử dụng khóa hoặc bằng chứng cốt lõi | Đưa vào backlog được theo dõi |

Thứ hạng phụ thuộc **impact × likelihood × exposure × asset criticality**, không phải bảng cứng. Một việc thiếu metadata có thể trở thành **HIGH** nếu nó ngăn khôi phục dữ liệu sau sự cố.

### 13.3. Không nhầm “có ngoại lệ” với “đã khắc phục”

Một finding có thể có trạng thái:

- **OPEN:** đã xác nhận sai lệch, chưa khắc phục.
- **IN_PROGRESS:** có người thực hiện, cần theo dõi tiến độ.
- **MITIGATED:** đã áp dụng biện pháp giảm rủi ro tạm thời.
- **ACCEPTED_RISK:** risk owner có thẩm quyền chấp nhận rủi ro trong phạm vi/hạn định.
- **READY_FOR_RETEST:** người sửa tuyên bố đã hoàn tất.
- **RESOLVED_VERIFIED:** người kiểm tra độc lập xác nhận kết quả.
- **CLOSED_NOT_APPLICABLE:** loại khỏi phạm vi với lý do và approval đúng.

Chỉ đánh dấu **RESOLVED_VERIFIED** khi có evidence và retest tương ứng. **Không xóa finding cũ** sau khi sửa cấu hình; lịch sử giúp chứng minh hiệu quả cải tiến và phát hiện tái diễn.

### 13.4. Nguyên tắc chọn remediation

- **Policy chưa rõ:** cập nhật profile hoặc runbook qua approval.
- **Code sai primitive:** sửa code/config, bổ sung unit/negative tests.
- **KMS grant quá rộng:** giảm effective permission, thu hồi token/quyền thừa, audit sử dụng trước đó.
- **Key usage đã bị lộ:** incident response, đánh giá DEK/KEK/signatures affected, rekey/re-encrypt nếu cần.
- **Backup thiếu KEK:** lập recovery plan và kiểm thử restore; không hủy dữ liệu cũ tùy tiện.
- **Trust store bị tráo:** khôi phục tin cậy, kiểm tra thông điệp/kết nối đã xác thực sai.
- **Policy exception hết hạn:** đóng đường legacy/đưa vào quy trình risk acceptance mới có deadline.
- **Crypto profile không còn phù hợp:** thiết kế migration từng giai đoạn thay vì tự hạ cấp.

Nếu chỉ có hành động **“rotate key”** cho mọi finding, tổ chức có thể chưa xử lý nguyên nhân: grants quá rộng, sai AAD, mất backup, nguy cơ key logging hoặc thiếu phân quyền nghiệp vụ.

## 14. Quy trình review từ chuẩn bị đến sign-off

Một chương trình review có thể được tổ chức thành một vòng có kiểm tra độc lập.

~~~mermaid
flowchart TD
    A["Trigger: lịch định kỳ hoặc thay đổi/sự cố"] --> B["Định nghĩa scope + policy version + owners"]
    B --> C["Thu snapshot inventory, KMS/HSM, IAM, TLS, code, audit"]
    C --> D["Kiểm tra đủ nguồn, thời điểm, tính toàn vẹn evidence"]
    D --> E{"Evidence đủ?"}
    E -->|"Chưa"| F["INSUFFICIENT_EVIDENCE; yêu cầu bổ sung"]
    F --> C
    E -->|"Đủ"| G["Đối chiếu requirements + effective controls"]
    G --> H["Findings: PASS/FAIL/EXCEPTION/risk"]
    H --> I{"Có rủi ro nghiêm trọng đang diễn ra?"}
    I -->|"Có"| INC["Incident response và containment ngay"]
    I -->|"Không"| J["Remediation plan + owner + deadline"]
    INC --> J
    J --> K["Implement qua change control"]
    K --> L["Independent retest + refreshed evidence"]
    L --> M{"Đạt closure criteria?"}
    M -->|"Không"| J
    M -->|"Có"| N["Sign-off + risk acceptance còn lại"]
    N --> O["Lưu review packet + giám sát drift đến kỳ tới"]
~~~

### 14.1. Chuẩn bị

1. Xác định **policy version** và phạm vi không nhập nhằng.
2. Phân loại **key types/datasets/regions/tenants**.
3. Lập control matrix với control ID, evidence requirement, pass criteria.
4. Bổ nhiệm reviewer không tự xác nhận những thay đổi của mình.
5. Đặt mốc deadline, escalation và phương án khi không thu đủ evidence.
6. Xác định quyền **read-only** để thu bằng chứng không lộ secret.

### 14.2. Thực hiện

1. Thu snapshot **inventory và actual key list**.
2. Đối soát **key ID/version, owner/custodian, state, purpose, cryptoperiod**.
3. Kiểm tra KMS/HSM attrs, key grants, IAM, service account và backup pathways.
4. Đối chiếu **algorithm profiles, source/config, TLS trust, key schedule**.
5. Thử các trường hợp **deny/fail-closed**, không chỉ happy path.
6. Kiểm tra restore, rollback, replay, sai tenant, quyền Sign/Decrypt.
7. Kiểm tra exceptions và tiến độ migration.
8. Ghi findings với evidence và impact thực tế.

### 14.3. Sign-off

Một review có thể kết thúc dưới các trạng thái quản trị khác nhau:

- **PASS:** những yêu cầu bắt buộc đạt theo phạm vi/evidence.
- **PASS WITH OPEN REMEDIATIONS:** có findings đã được đánh giá rủi ro, có kế hoạch/approvals đủ điều kiện theo governance.
- **CONDITIONAL ACCEPTANCE:** phụ thuộc biện pháp tạm thời có hạn.
- **FAIL / ESCALATED:** có rủi ro không thể chấp nhận hoặc thiếu bằng chứng trọng yếu.

**Không dùng một status PASS chung để che các findings còn tồn tại.** Sign-off phải nêu rõ residual risk và các mục phải tiếp tục theo dõi.

## 15. Mẫu review packet và ma trận điều khiển

Một bản tổng kết tốt cho phép người không tham gia đợt review **hiểu phạm vi, kết luận, hạn chế, bằng chứng và quyết định**.

### 15.1. Mẫu review packet

~~~yaml
reviewId: crypto-policy-review-billing-example
reviewType: periodic-and-triggered
service: billing
module: SECURITY_KEY_MANAGEMENT_FUNDAMENTALS
environment: production
policyId: corporate-cryptographic-policy
policyVersion: v3
reviewAsOf: "2026-11-28"
scope:
  services:
    - payment-api
    - billing-worker
  keyClasses:
    - DEK
    - KEK
    - SIGNING
    - HMAC
  providers:
    - approved-kms
  dataClass: confidential
roles:
  reviewLeadRole: security-architecture
  keyOwnerRole: billing-platform
  custodianRole: crypto-operations
  independentReviewerRole: security-assurance
coverage:
  inventoryPopulation: 120
  inspectedKeyMetadata: 120
  manualHighRiskSamples: 18
  scopeLimitation: "Không kiểm thử toàn bộ lịch sử ciphertext"
summary:
  passedControls: 37
  failedControls: 3
  insufficientEvidence: 1
  validExceptions: 2
  expiredExceptions: 1
  decision: CONDITIONAL_ACCEPTANCE
findings:
  - id: F-001
    control: IAM-KMS-04
    keyRef: "kms://example/billing-kek-v3"
    severity: HIGH
    ownerRole: platform-security
    status: OPEN
    mitigationRef: "change/reduce-decrypt-grants"
  - id: F-002
    control: RECOVERY-02
    keyRef: "kms://example/legacy-kek"
    severity: HIGH
    ownerRole: crypto-operations
    status: READY_FOR_RETEST
evidenceManifestRef: "evidence-store://immutable/review-manifest"
approvalWorkflowRef: "change/review-signoff"
nextReviewTrigger: "next-periodic-window-or-material-change"
~~~

Dữ liệu chỉ minh họa, **không phản ánh một hệ thống thật**, không phải schema chuẩn và không thay bằng chứng actual. Không suy ra các tỷ lệ từ ví dụ cho hệ thống của người học.

### 15.2. Control register ngắn

| ID | Yêu cầu kiểm soát | Evidence tối thiểu | Kết quả nếu sai |
| --- | --- | --- | --- |
| **POL-01** | Policy version có hiệu lực và được phê duyệt | Registry + approval | FAIL/NOT_EVALUATED |
| **INV-01** | Mọi key có owner/custodian và purpose | Inventory + KMS key list | FINDING |
| **ALG-01** | New Encrypt/Sign dùng profile được duyệt | Code/config + KMS | FINDING |
| **AEAD-02** | Nonce strategy và tag check đúng | Design + tests | FINDING |
| **TRUST-03** | TLS/certificate/public verify key đúng trust | Config + tests | FINDING |
| **IAM-04** | Grants đúng key/action/tenant | Effective policy + samples | FINDING |
| **LIFE-05** | State/cryptoperiod/rotation đúng | Inventory + usage audit | FINDING |
| **REC-06** | Recovery có đủ key dependencies | Restore test | FINDING |
| **EXC-07** | Exception có expiry, scope, mitigation | Exception register | FINDING |
| **AUD-08** | Key use/policy changes có audit được bảo vệ | KMS/event evidence | FINDING |

ID là **mã điều khiển minh họa**, không phải tham chiếu tới một tiêu chuẩn bên ngoài.

### 15.3. Vì sao cần evidence manifest?

Một report PDF/Markdown có thể mô tả các kết luận, nhưng các evidence lớn thường ở nơi khác. **Evidence manifest** liên kết:

~~~text
Review ID
  ├── Policy baseline version + approval
  ├── Inventory snapshot ID + timestamp
  ├── KMS/HSM state + IAM grants snapshot
  ├── TLS/PKI test results
  ├── Code commit / CI test evidence
  ├── Restore exercise / key dependency report
  ├── Exceptions + risk approvals
  ├── Findings, remediation tickets, retests
  └── Sign-off + next review trigger
~~~

Nên bảo vệ manifest bằng cơ chế **kiểm soát sửa đổi/tính toàn vẹn** và quyền đọc. Không nhét key material, raw password hoặc plaintext vào packet chỉ vì muốn audit có “đủ dữ liệu”.

## 16. Ví dụ Java 17: tự động phát hiện policy drift từ metadata

Ví dụ này mô hình hóa **một vòng review metadata** giữa:

- **Approved inventory:** danh mục khóa và chính sách đã phê duyệt.
- **Observed snapshot:** kết quả đọc metadata KMS/IAM/restore/audit từ nguồn đáng tin.
- **Review baseline:** policy version, algorithm allowlist, nhóm principal được phép Decrypt.
- **Exception register:** ngoại lệ có approval, expiry và kiểm soát tạm thời.

Đây **không phải công cụ audit production** và không gọi KMS thật. Trong hệ thống thực, snapshot cần được thu từ **read-only APIs**, có source/time/integrity, tránh tin dữ liệu từ client và phải đối soát **effective permissions** chứ không chỉ những quyền được kê khai.

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class CryptoPolicyReviewDemo {

    enum State {
        ACTIVE, LEGACY_READ_ONLY, DISABLED, PENDING_DELETION
    }

    enum Operation {
        ENCRYPT, DECRYPT, SIGN, WRAP, UNWRAP
    }

    enum Severity {
        CRITICAL, HIGH, MEDIUM
    }

    record Baseline(
            String policyVersion,
            Set<String> approvedAlgorithms,
            Set<String> allowedDecryptPrincipals,
            int maxEvidenceAgeDays) {}

    record InventoryKey(
            String keyId,
            String ownerTeam,
            String custodianTeam,
            String purpose,
            State expectedState,
            LocalDate rotationDue,
            boolean requireNonExportable,
            boolean requireRecoveryTest,
            String approvedPolicyVersion) {}

    record ObservedKey(
            String keyId,
            String algorithm,
            State actualState,
            boolean exportable,
            Set<Operation> enabledOperations,
            Set<String> effectiveDecryptPrincipals,
            boolean restoreTestPassed,
            boolean auditEvidencePresent) {}

    record EvidenceSnapshot(
            LocalDate collectedAt,
            List<ObservedKey> observedKeys) {}

    record PolicyException(
            String keyId,
            String controlId,
            LocalDate expiresAt,
            boolean approved,
            boolean compensatingControlsVerified) {}

    record Finding(
            String controlId,
            String keyId,
            Severity severity,
            String explanation) {}

    private static void add(
            List<Finding> findings, String control,
            String keyId, Severity severity, String explanation) {
        findings.add(
            new Finding(control, keyId, severity, explanation));
    }

    // Đánh giá metadata. Không bao giờ đọc hoặc ghi raw keys.
    static List<Finding> review(
            LocalDate reviewDate,
            Baseline baseline,
            List<InventoryKey> inventory,
            EvidenceSnapshot evidence,
            List<PolicyException> exceptions) {

        List<Finding> findings = new ArrayList<>();
        Map<String, ObservedKey> actualById = new HashMap<>();

        for (ObservedKey observed : evidence.observedKeys()) {
            ObservedKey previous =
                actualById.putIfAbsent(observed.keyId(), observed);
            if (previous != null) {
                add(findings, "EVIDENCE-DUPLICATE",
                    observed.keyId(), Severity.MEDIUM,
                    "Repeated key reference in observed snapshot");
            }
        }

        long evidenceAge = ChronoUnit.DAYS.between(
            evidence.collectedAt(), reviewDate);
        if (evidenceAge < 0 ||
                evidenceAge > baseline.maxEvidenceAgeDays()) {
            add(findings, "EVIDENCE-FRESHNESS",
                "*", Severity.HIGH,
                "Evidence snapshot is outside accepted review window");
        }

        Set<String> expectedIds = new java.util.HashSet<>();

        for (InventoryKey key : inventory) {
            if (!expectedIds.add(key.keyId())) {
                add(findings, "INV-DUPLICATE",
                    key.keyId(), Severity.MEDIUM,
                    "Duplicate inventory key ID");
            }

            if (key.ownerTeam() == null ||
                    key.ownerTeam().isBlank() ||
                    key.custodianTeam() == null ||
                    key.custodianTeam().isBlank()) {
                add(findings, "INV-OWNERSHIP",
                    key.keyId(), Severity.MEDIUM,
                    "Owner/custodian missing");
            }

            if (!baseline.policyVersion()
                    .equals(key.approvedPolicyVersion())) {
                add(findings, "POLICY-VERSION",
                    key.keyId(), Severity.MEDIUM,
                    "Inventory uses another policy baseline");
            }

            ObservedKey observed = actualById.get(key.keyId());
            if (observed == null) {
                add(findings, "INV-MISSING-ACTUAL",
                    key.keyId(), Severity.HIGH,
                    "Inventory reference absent from observed KMS snapshot");
                continue;
            }

            if (!baseline.approvedAlgorithms()
                    .contains(observed.algorithm())) {
                add(findings, "ALG-ALLOWLIST",
                    key.keyId(), Severity.HIGH,
                    "Algorithm not approved by baseline");
            }

            if (key.expectedState() != observed.actualState()) {
                add(findings, "KEY-STATE",
                    key.keyId(), Severity.HIGH,
                    "Actual state differs from approved inventory");
            }

            if (key.requireNonExportable() && observed.exportable()) {
                add(findings, "KEY-EXPORTABILITY",
                    key.keyId(), Severity.CRITICAL,
                    "High-value key is exportable against policy");
            }

            if (observed.actualState() == State.ACTIVE &&
                    key.rotationDue() != null &&
                    key.rotationDue().isBefore(reviewDate)) {
                add(findings, "ROTATION-DUE",
                    key.keyId(), Severity.MEDIUM,
                    "Rotation milestone overdue; examine cryptoperiod");
            }

            if (key.requireRecoveryTest()
                    && !observed.restoreTestPassed()) {
                add(findings, "RECOVERY-TEST",
                    key.keyId(), Severity.HIGH,
                    "Required key-dependent restore test is not verified");
            }

            if (!observed.auditEvidencePresent()) {
                add(findings, "AUDIT-EVIDENCE",
                    key.keyId(), Severity.HIGH,
                    "Required key-usage audit evidence missing");
            }

            if (observed.enabledOperations()
                    .contains(Operation.DECRYPT)) {
                for (String principal :
                        observed.effectiveDecryptPrincipals()) {
                    if (!baseline.allowedDecryptPrincipals()
                            .contains(principal)) {
                        add(findings, "IAM-DECRYPT",
                            key.keyId(), Severity.HIGH,
                            "Unapproved effective Decrypt principal: "
                                + principal);
                    }
                }
            }
        }

        // Kiểm tra cả chiều actual -> inventory.
        for (ObservedKey observed : evidence.observedKeys()) {
            if (!expectedIds.contains(observed.keyId())) {
                add(findings, "INV-UNREGISTERED",
                    observed.keyId(), Severity.HIGH,
                    "KMS key absent from approved inventory");
            }
        }

        // Ngoại lệ hết hạn hoặc thiếu approval là finding RIÊNG,
        // không tự biến finding kỹ thuật thành PASS.
        for (PolicyException exception : exceptions) {
            if (!exception.approved() ||
                    exception.expiresAt().isBefore(reviewDate) ||
                    !exception.compensatingControlsVerified()) {
                add(findings, "EXCEPTION-CONTROL",
                    exception.keyId(), Severity.HIGH,
                    "Exception invalid, expired or mitigations unverified: "
                        + exception.controlId());
            }
        }

        return List.copyOf(findings);
    }

    public static void main(String[] args) {
        LocalDate asOf = LocalDate.of(2026, 11, 28);

        Baseline baseline = new Baseline(
            "crypto-policy-v3",
            Set.of("AES-256-GCM", "Ed25519"),
            Set.of("billing-reader-prod"),
            7);

        List<InventoryKey> inventory = List.of(
            new InventoryKey(
                "billing-kek-v3", "billing-platform",
                "crypto-operations", "wrap-billing-deks",
                State.ACTIVE, LocalDate.of(2026, 10, 31),
                true, true, "crypto-policy-v3"),
            new InventoryKey(
                "release-signing-v2", "release-engineering",
                "security-key-custodian", "sign-release",
                State.ACTIVE, LocalDate.of(2027, 3, 1),
                true, false, "crypto-policy-v3"));

        EvidenceSnapshot snapshot = new EvidenceSnapshot(
            asOf, List.of(
                new ObservedKey(
                    "billing-kek-v3", "AES-256-GCM", State.ACTIVE,
                    false, Set.of(Operation.WRAP, Operation.UNWRAP,
                        Operation.DECRYPT),
                    Set.of("billing-reader-prod", "unknown-batch"),
                    false, true),
                new ObservedKey(
                    "release-signing-v2", "Ed25519", State.ACTIVE,
                    true, Set.of(Operation.SIGN),
                    Set.of(), false, true)));

        List<PolicyException> exceptions = List.of(
            new PolicyException(
                "legacy-payment-v1", "ALG-LEGACY",
                LocalDate.of(2026, 10, 1), true, true));

        List<Finding> findings =
            review(asOf, baseline, inventory, snapshot, exceptions);

        System.out.println("Findings: " + findings.size());
        for (Finding finding : findings) {
            System.out.println(
                finding.severity() + " | " +
                finding.controlId() + " | " +
                finding.keyId() + " | " +
                finding.explanation());
        }
    }
}
~~~

Kết quả minh họa có các findings như:

~~~text
MEDIUM | ROTATION-DUE | billing-kek-v3 | ...
HIGH | RECOVERY-TEST | billing-kek-v3 | ...
HIGH | IAM-DECRYPT | billing-kek-v3 | ...
CRITICAL | KEY-EXPORTABILITY | release-signing-v2 | ...
HIGH | EXCEPTION-CONTROL | legacy-payment-v1 | ...
~~~

### 16.1. Những điểm quan trọng trong code

1. **Inventory và observed snapshot là hai nguồn khác nhau**: kiểm tra cả missing actual và unregistered actual.
2. **Key owner/custodian phải hiện diện**; field rỗng là dấu hiệu quản trị không hoàn chỉnh.
3. **Policy version** được đối chiếu trước khi kết luận.
4. **Algorithm allowlist** dùng tập do reviewer xác định, không do client yêu cầu.
5. **Key state** thực tế phải khớp inventory đã được phê duyệt.
6. **Exportability** cần kiểm tra đối với khóa có yêu cầu non-exportable.
7. **Rotation due** tạo finding, **không tự động destroy key**.
8. **Restore test và audit evidence** là yêu cầu tách biệt với key algorithm.
9. **Effective Decrypt principals** được kiểm tra với danh sách quyền đã duyệt.
10. **Exception expired/không được duyệt** được nêu thành finding, không làm sạch kết quả.
11. Code chỉ báo **metadata/sai lệch**, không đọc hoặc in DEK/KEK/private keys.
12. Output thích hợp cho quy trình **review & triage**, không được tự động cấp quyền hay xóa khóa.

### 16.2. Những giới hạn không được bỏ qua

- **Snapshot trong main là dữ liệu giả lập**. Một tool thực phải xác minh nguồn, thời điểm, integrity, pagination và account/region coverage.
- **Danh sách allowedDecryptPrincipals toàn cục** chỉ mang tính minh họa. Production nên ràng buộc **principal–key ID–purpose–tenant–operation**, bao gồm quyền kế thừa và key policy.
- **Tên algorithm của KEK và Sign** khác nhau theo API/provider; danh sách thuật toán phải ánh xạ đúng key type và usage. Mẫu kiểm tra allowlist không đủ chứng minh tính an toàn của primitive.
- **Một lỗi restoreTestPassed=false** chỉ cho biết thiếu/bị lỗi bằng chứng theo mô hình; cần kiểm tra thực tế, không được suy diễn ngay rằng mất dữ liệu.
- **Chỉ nhìn boolean exportable** không phản ánh tất cả ranh giới import/export/backup của HSM.
- **Không kiểm tra nonce uniqueness, AAD, TLS, chữ ký, business authorization hay replay bằng cách đọc metadata đơn giản**; cần tests/threat assessment riêng.
- **Không có transaction/identity/exception approval thực**. Khi chạy production, approval và evidence phải được xác minh qua hệ thống đáng tin.
- **Review clock và timezone** phải thống nhất; kết quả liên quan đến ngày/expiry cần rõ mốc hiệu lực.
- Dữ liệu audit có thể chứa thông tin nhạy cảm; không in toàn bộ IAM/payload không cần thiết ra public CI logs.

Mục đích của ví dụ là **tự động hóa những kiểm tra lặp lại để reviewer tập trung vào quyết định rủi ro**, không biến một đoạn Java thành “bộ kiểm định mật mã” hoàn chỉnh.

## 17. Tình huống A: KMS grant mở rộng quyền Decrypt

### 17.1. Bối cảnh

BillingService dùng một KEK để bọc DEK cho nhiều tenant. Key non-exportable trong KMS và inventory đầy đủ. Một lần xử lý sự cố, đội vận hành cấp thêm một role **billing-maintenance** có quyền Decrypt trên nhiều key rồi quên thu hồi.

### 17.2. Review phát hiện gì?

- **Inventory:** key owner/custodian và purpose hợp lệ.
- **KMS actual:** key vẫn ACTIVE, non-exportable.
- **IAM effective permissions:** role bổ sung có Decrypt không nằm trong allowed principals.
- **Key usage audit:** có các lần gọi Decrypt ngoài cửa sổ bảo trì.
- **Application authorization:** chưa biết role có thể đọc tài nguyên của tenant nào.
- **Finding:** key material có thể chưa bị xuất, nhưng **key usage compromise** là rủi ro thật.

### 17.3. Remediation

1. Kiểm tra xem các lệnh Decrypt có hợp lệ và đã ảnh hưởng dữ liệu nào không.
2. Thu hồi grant hoặc credential sau đánh giá/containment.
3. Điều tra DEK/plaintext có bị lấy và còn nằm trong cache/log/dump không.
4. Tách service account, giới hạn key ID/tenant/action và thời hạn cho maintenance.
5. Thêm kiểm tra **temporary grants** vào review định kỳ và alert.
6. Đóng finding bằng **IAM snapshot mới + tests DENY + audit**; không chỉ gỡ quyền trong một ticket.

**Không mặc định rằng rotate KEK sẽ sửa lỗi cấp quyền.** Nếu role vẫn có Decrypt trên KEK mới, lỗ hổng vẫn tồn tại.

## 18. Tình huống B: DEK/KEK rotation và backup lịch sử

### 18.1. Bối cảnh

Một tổ chức đã rotate KEK-v1 sang KEK-v2. Dữ liệu mới dùng KEK-v2 để bọc DEK. Key custodian chuẩn bị hủy KEK-v1. Review phát hiện một kho backup offline còn nhiều **wrapped DEK** dùng KEK-v1.

### 18.2. Quyết định của reviewer

Không được chọn **Destroy KEK-v1** chỉ vì data path mới đã chuyển sang v2. Cần:

- Liệt kê backup/snapshot có KEK-v1 dependency.
- Xem những bản backup đó còn trong retention hợp lệ không.
- Xác định có thể **restore, unwrap, rewrap hoặc re-encrypt** những bản sao cần giữ không.
- Thử đường khôi phục bao gồm **nonce/tag/AAD/key version/context**, không chỉ kiểm tra checksum.
- Có owner approval và risk record khi cần thay đổi retention/migration.
- Chỉ hủy theo chính sách sau khi dependency đã được giải quyết và chứng minh.

### 18.3. Finding mẫu

~~~text
Control: RECOVERY-KEY-DEPENDENCY
Expected: Không destroy KEK nếu dữ liệu/backups còn phụ thuộc
Actual: KEK-v1 đang chờ hủy, backup B-201 còn wrapped DEK dưới v1
Impact: Mất khả năng khôi phục bản sao B-201
Action: Block deletion; migrate và thử restore; phê duyệt lại
Closure: Restore evidence + updated key inventory + independent check
~~~

Tình huống này cho thấy policy review liên quan trực tiếp đến **availability**, không chỉ confidentiality.

## 19. Tình huống C: TLS và signing key bị cấu hình lệch

### 19.1. Bối cảnh

PaymentAPI có policy yêu cầu peer authentication, TLS profile được phê duyệt và private signing key ở HSM. Một bản deploy mới:

- Tắt hostname validation vì certificate backend bị đổi tên.
- Bật cơ chế xuất **TLS traffic secrets** trong chế độ debug.
- Dùng một signing key cho cả release manifest và webhook mà không có purpose gate.
- Verification service lấy public key từ một URL tùy ý được yêu cầu ký đính kèm.

### 19.2. Vì sao chỉ kiểm tra thuật toán là không đủ?

Các primitive vẫn có thể là TLS 1.3 và Ed25519. Nhưng:

- Bỏ **hostname validation** có thể tạo điều kiện MITM.
- Traffic secret logging có thể làm lộ lịch sử lưu lượng nếu attacker có logs.
- Sign API quá rộng cho phép tạo chữ ký trên nội dung ngoài dự định.
- Public key từ nguồn chưa tin cậy cho phép attacker tự ký và tự xác minh.

### 19.3. Hướng xử lý

- Khôi phục trust/hostname validation đúng nguồn, kiểm tra certificate chain.
- Vô hiệu hóa và quản trị chặt key logging/debug trong production; điều tra bản log đã tạo.
- Tách signing key hoặc áp dụng purpose-specific signing service/IAM.
- Cố định trusted issuer/verification key source; không dùng URL do payload tự khai.
- Bổ sung **negative tests** vào CI và runtime config checks.
- Nếu có nghi ngờ bị MITM hoặc ký giả, kích hoạt điều tra sự cố song song với review.

Một kết luận **“TLS 1.3 và Ed25519 được bật”** không đủ để đánh dấu các controls này PASS.

## 20. Các chỉ số đánh giá hiệu quả của policy review

Các chỉ số hữu ích nhất là những chỉ số **dẫn tới hành động**.

| Chỉ số | Ý nghĩa | Cảnh báo khi |
| --- | --- | --- |
| **Inventory coverage** | Tỷ lệ khóa actual được đăng ký/định danh đầy đủ | Xuất hiện key orphan/unknown |
| **Owner/custodian coverage** | Khóa có người chịu trách nhiệm hợp lệ | Người cũ đã rời nhóm hoặc không có backup custodian |
| **Effective grant drift** | Quyền thực tế khác baseline | Decrypt/Sign/Unwrap xuất hiện role không được phê duyệt |
| **Overdue rotation/review** | Key quá hạn theo policy | Có key ACTIVE dùng cho tác vụ mới sau cryptoperiod |
| **Exception expiry rate** | Ngoại lệ quá hạn hoặc thiếu mitigation | Legacy profile còn được tạo mới |
| **Recovery-test coverage** | Khả năng restore dữ liệu mã hóa được kiểm chứng | Key dependencies không có restore evidence |
| **TLS/trust profile conformance** | Endpoint dùng đúng profile và identity validation | Certificate check bị vô hiệu hóa |
| **Findings mean time to remediate** | Tốc độ giải quyết rủi ro | High-risk findings mở kéo dài |
| **Repeat findings** | Lỗi cũ quay lại | Cùng sai lệch tái xuất hiện sau closure |
| **Evidence completeness** | Tỷ lệ controls đủ evidence có nguồn | PASS không có bằng chứng |
| **Break-glass/grant hygiene** | Quyền khẩn cấp có được thu hồi | Grant vượt hạn, không có ticket |
| **Unreviewed crypto changes** | Triển khai thuật toán/provider không qua approval | Version/profile không có trong registry |

**Không tối ưu để mọi dashboard luôn xanh** bằng cách bỏ qua môi trường hoặc thay điều kiện PASS. Review nên giữ **denominator/population** rõ ràng; ví dụ 95% inventory coverage nghĩa là còn 5% **chưa được kiểm kê**, chứ không mặc nhiên là 5% vô hại.

### 20.1. Dùng tự động hóa hợp lý

Những việc dễ tự động hóa:

- Liệt kê actual keys và đối soát với inventory.
- Kiểm tra key states, policy versions và rotateDue.
- So sánh effective grants với allowlist.
- Phát hiện exceptions hết hạn.
- Kiểm tra expiry certificate và approved TLS configurations.
- Tạo bằng chứng CI negative tests.
- Theo dõi recovery-test records và đánh dấu quá hạn.

Những việc cần phân tích con người hoặc assessment chuyên sâu:

- Chứng minh AAD ràng buộc đúng với business authorization thực tế.
- Đánh giá threat model và blast radius khi root/KEK lộ.
- Quyết định một ngoại lệ có chấp nhận được không.
- Đánh giá crypto-agility, migration và tính tương thích.
- Phân loại incident vs configuration defect.
- Phê duyệt key destruction hoặc thay trust root.

Automation nên **đưa ra bằng chứng và finding**, không tự hủy key hay cấp quyền trên production nếu chưa có thiết kế kiểm soát tác động phù hợp.

## 21. Những lỗi thường gặp trong policy review

| Sai lầm | Vì sao làm review kém hiệu quả? | Cách khắc phục |
| --- | --- | --- |
| **Chỉ đọc tài liệu, không xem runtime** | Không phát hiện policy drift | Đối chiếu config, KMS, IAM, usage |
| **Chỉ hỏi key owner xác nhận** | Evidence có thể thiên lệch/thiếu | Thu nguồn độc lập và snapshot |
| **Không đóng băng policy version** | So sánh nhầm baseline | Ghi version, effective dates |
| **PASS khi thiếu evidence** | Che lỗ hổng chưa được kiểm tra | INSUFFICIENT_EVIDENCE/NOT_EVALUATED |
| **Chỉ xem khóa trong inventory** | Bỏ sót key tạo ngoài quy trình | Đối soát actual → inventory và ngược lại |
| **Chỉ xem key algorithm** | Bỏ qua nonce, AAD, trust, IAM | Review theo use case và key lifecycle |
| **Cho KMS non-exportable = an toàn tuyệt đối** | Decrypt/Sign qua API vẫn có thể bị lạm dụng | Review effective permissions/usage |
| **Không xác định key custodian** | Rotation/khôi phục thiếu đầu mối | Owner, custodian, escalation rõ |
| **Đếm ciphertext không đọc được là “mã hóa an toàn”** | Có thể mất KEK/metadata | Restore tests và key dependencies |
| **Thấy rotate xong nên đóng finding lộ DEK** | Raw DEK cũ có thể vẫn dùng mở dữ liệu | Đánh giá re-encrypt và dữ liệu đã lộ |
| **Ngoại lệ không hết hạn** | Legacy tồn tại vô thời hạn | Scope, expiry, risk owner, migration |
| **Chỉ test happy path** | Không phát hiện bypass/fail-open | Negative tests |
| **Đóng finding bằng lời hứa** | Không có hiệu lực khắc phục | Retest và evidence mới |
| **Reviewer tự duyệt sửa lỗi của mình** | Xung đột lợi ích | Independent verification phù hợp |
| **Ghi raw secret vào ticket** | Review tự gây rò rỉ | Chỉ metadata/evidence references |
| **Chỉ quan sát CI, không xét runtime** | Grants và config thay sau deploy | Runtime drift monitoring |
| **Không xét resumption/0-RTT** | Kết luận FS/TLS quá rộng | Review handshake mode/policy thật |
| **Không xét public key trust** | Signature Verify đúng với khóa của attacker | Trusted PKI/JWKS/issuer mapping |
| **Không có deadline/remediation owner** | Finding bị bỏ mặc | SLA theo severity và escalation |
| **Gộp security review với incident containment** | Trì hoãn ngăn rủi ro đang xảy ra | Incident response ngay khi cần |

## 22. Checklist thực hiện policy review

### Chuẩn bị review

1. Có **policy owner**, review lead, independent reviewer và approver phù hợp?
2. Policy baseline/version và ngày hiệu lực đã được khóa cho kỳ review?
3. Scope có service, environment, region, tenant, data class và trust boundaries?
4. Có lịch review định kỳ **và** trigger review sau thay đổi/sự cố?
5. Có danh sách control IDs, pass criteria và evidence requirements?
6. Có chính sách xử lý **NOT_EVALUATED, INSUFFICIENT_EVIDENCE, EXCEPTION**?
7. Có quyền thu evidence **read-only**, không yêu cầu raw secrets?
8. Có quy tắc severity, escalation và deadline cho findings?

### Key inventory, lifecycle và quyền

9. Actual KMS/HSM keys đã được đối soát **hai chiều** với inventory?
10. Mỗi key có owner/custodian/purpose/key ID/version/state hợp lệ?
11. Key thuật toán/key type/exportability phù hợp với approved profile?
12. Không còn root/KEK/signing key tạo ngoài quy trình?
13. Effective IAM grants đã được kiểm tra, gồm role kế thừa và temporary grants?
14. Encrypt/Decrypt/Sign/Unwrap/Derive/Export được cấp theo đúng purpose?
15. Business authorization và tenant/resource mapping độc lập với KMS IAM?
16. Key cryptoperiod và rotateDue có được thực thi theo loại operation?
17. Legacy read-only/decrypt-only có được quản lý đúng khi provider không hỗ trợ state native?
18. Key retired/revoked có còn bị dùng cho thao tác mới không?
19. DEK/KEK rewrap/re-encrypt có được phân biệt với rotation signing key/session key?
20. Backup còn đủ wrapped DEK, KEK, context, nonce/tag và metadata?
21. Restore test có **thực sự mở được dữ liệu** và có evidence?
22. Hủy khóa có owner approval, dependency check và policy về recovery materials?

### Thuật toán và giao thức

23. AEAD modes, nonce strategy, AAD encoding và tag validation có đúng profile?
24. Tất cả lỗi tag/certificate/key state đều **fail closed**?
25. Signing/verification có key purpose và trusted public key source?
26. HMAC không bị chia raw key cho bên chỉ cần Verify?
27. Password-based KDF có salt, cost/version, không dùng password trực tiếp làm AES key?
28. HKDF và agreement có domain separation, peer authentication, ephemeral lifecycle?
29. TLS profile thực tế có certificate/hostname/mTLS khi cần và không bị bypass?
30. PSK/resumption/0-RTT/forward secrecy được đánh giá theo chế độ thật?
31. Có cơ chế chống replay/rollback ở tầng giao thức/nghiệp vụ khi cần?
32. Legacy algorithms có phạm vi đọc dữ liệu cũ được phép, không cho tạo dữ liệu mới?

### Bằng chứng, remediation và cải tiến

33. Evidence có timestamp/source/scope/integrity và không chứa secret?
34. Có test coverage thích hợp cho **negative paths**?
35. Runtime grants/config có được kiểm tra sau deploy, không chỉ qua CI?
36. Exceptions có risk approval, mitigations, expiration và migration deadline?
37. Findings có severity, expected/actual, owner, dueAt và evidence refs?
38. High/Critical findings đang diễn ra đã chuyển incident response khi cần?
39. Closure có **retest độc lập** và snapshot mới?
40. Kết quả sign-off có nêu rõ residual risk, phạm vi chưa kiểm tra và open actions?
41. Audit logs/manifest được bảo vệ khỏi sửa/xóa, không log raw keys?
42. Có metrics về drift, overdue keys, recovery failures và findings tái diễn?
43. Crypto-agility được xem xét khi threat model/provider/chuẩn thay đổi?
44. Review packet có thể truy vết lại theo **review ID, policy version, evidence và approvals**?

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Chính sách công ty ghi “mọi DEK phải được KMS bảo vệ”. Chỉ đọc nội dung tài liệu có đủ để kết luận PASS?

**Đáp án:** Không. Cần evidence từ kiến trúc, storage envelope, KMS keys/grants, code paths và dữ liệu thực tế. Policy review kiểm tra cả **yêu cầu và hiệu lực thực thi**.

**Câu 2.** Một key có tên trong inventory nhưng không xuất hiện trong snapshot KMS. Phải làm gì?

**Đáp án:** Ghi discrepancy và điều tra scope, region, permissions, deletion/state, key version và nguồn evidence. Không tự đánh dấu PASS hay xóa record inventory để làm khớp.

**Câu 3.** Một key non-exportable nhưng workload có quyền Unwrap/Decrypt rất rộng. Có nguy cơ không?

**Đáp án:** Có. Attacker có thể lạm dụng API để lấy plaintext DEK hoặc dữ liệu mà không export KEK. Review cần kiểm tra **effective permissions và audit key usage**.

**Câu 4.** Tại sao policy review phải kiểm tra nonce AES-GCM chứ không chỉ key size?

**Đáp án:** Tái sử dụng nonce dưới cùng khóa GCM có thể phá tính bí mật và toàn vẹn bất kể khóa 128 hay 256 bit. Policy phải bao gồm **cách cấp nonce, giới hạn sử dụng và fail-closed**.

**Câu 5.** Lịch review hàng quý có đủ khi private signing key bị nghi lộ vào ngày đầu quý?

**Đáp án:** Không. Phải kích hoạt **incident response ngay** và thực hiện review theo sự kiện để đánh giá nguyên nhân/controls. Review định kỳ không thay containment.

**Câu 6.** Một exception legacy có approval nhưng đã qua ngày hết hạn. Có được đánh dấu “valid exception” không?

**Đáp án:** Không. Cần đánh dấu **expired**, đánh giá rủi ro, chặn đường tạo dữ liệu mới nếu policy yêu cầu và làm lại quy trình phê duyệt/migration, không tự gia hạn.

**Câu 7.** Backup ciphertext có SHA-256 checksum khớp. Vì sao vẫn cần kiểm tra KEK?

**Đáp án:** Checksum không bảo đảm có thể giải mã. Phải có **wrapped DEK, KEK/version, KMS context, nonce/tag/AAD** và quyền/khả năng restore phù hợp.

**Câu 8.** Đã rotate KEK nhưng raw DEK cũ bị lộ. Việc rewrap cùng DEK có đủ không?

**Đáp án:** Không. Attacker có DEK cũ có thể đọc ciphertext tương ứng; cần đánh giá thay **DEK và re-encrypt**, cùng dữ liệu đã bị sao chép.

**Câu 9.** Vì sao review phải xét cả policy adequacy và implementation conformance?

**Đáp án:** Một chính sách có thể thiếu yêu cầu chống replay hoặc nguồn trust dù code tuân theo mọi điều ghi trong đó. Ngược lại, chính sách đúng nhưng KMS grants quá rộng vẫn gây rủi ro. Cả **tính phù hợp lẫn hiệu lực** đều quan trọng.

**Câu 10.** Khi auditor không thu được grants của một HSM partition, có thể PASS phần đó vì không thấy sự cố?

**Đáp án:** Không. Phải ghi **INSUFFICIENT_EVIDENCE hoặc NOT_EVALUATED**, yêu cầu quyền/evidence bổ sung và nêu limitation trong sign-off.

**Câu 11.** Một test ký và Verify Ed25519 thành công có chứng minh đúng signer identity không?

**Đáp án:** Chưa. Public verification key phải đến từ **nguồn được tin và ràng buộc đúng issuer/purpose**. Attacker có thể tự tạo cặp khóa và Verify thành công với khóa của họ.

**Câu 12.** Vì sao tự động hóa review không nên tự gọi KMS Delete cho những key có rotateDue quá hạn?

**Đáp án:** Key có thể vẫn cần mở ciphertext hoặc backup lịch sử. Phải xem **cryptoperiod theo operation, key dependencies, restore test và approval** trước khi hủy.

**Câu 13.** Một đợt review tìm thấy ba findings HIGH, đã có ticket sửa nhưng chưa retest. Có thể ghi RESOLVED_VERIFIED không?

**Đáp án:** Không. Ticket và lời xác nhận của owner chưa đủ. Cần **evidence mới và xác minh độc lập**; trong lúc đó finding còn OPEN/IN_PROGRESS/READY_FOR_RETEST tùy tình hình.

**Câu 14.** Review phát hiện TLS 1.3 đang bật, có thể kết luận mọi traffic đều có forward secrecy không?

**Đáp án:** Không. Phải xem **(EC)DHE, PSK-only, PSK+DHE, 0-RTT** và quản lý session secrets. Protocol version string không chứng minh mọi nhánh handshake có FS giống nhau.

**Câu 15.** Có thể coi KMS encryption context là sự thay thế toàn bộ business authorization cho tenant không?

**Đáp án:** Không. Context có thể bổ sung ràng buộc wrapped DEK, nhưng ứng dụng vẫn phải kiểm tra **principal và quyền trên tài nguyên**. AAD của data ciphertext cũng là kiểm soát khác.

**Câu 16.** Policy review có nên lưu raw DEK hoặc private key để “làm bằng chứng” về trạng thái không?

**Đáp án:** Không. Dùng **key references, attributes, audit events, operation results và evidence có kiểm soát**. Việc xuất raw secrets chỉ để kiểm tra làm tăng rủi ro.

**Câu 17.** Một key nằm trong inventory, nhưng owner đã nghỉ việc. Review cần làm gì ngoài đổi tên owner?

**Đáp án:** Phải kiểm tra **custodian, kế hoạch bàn giao, grants, token/smart cards, recovery shares và approval chain**. Đổi metadata không tự thu hồi quyền thực tế.

**Câu 18.** Vì sao finding “key policy drift” không thể luôn được giải quyết bằng rotate key?

**Đáp án:** Drift có thể là **quyền Decrypt quá rộng, trust sai, code thiếu AAD, exception quá hạn hoặc backup thiếu KEK**. Mỗi nguyên nhân có remediation riêng; rotation chỉ đúng cho một số trường hợp.

**Câu 19.** Thế nào là một review sign-off trung thực?

**Đáp án:** Nó ghi rõ **scope, baseline version, coverage, evidence limitations, findings còn mở, residual risks, exceptions, người phê duyệt và hành động tiếp theo**, thay vì một dấu PASS che mọi thiếu sót.

**Câu 20.** Crypto-agility liên quan gì đến policy review?

**Đáp án:** Review định kỳ đánh giá liệu profile/thuật toán/giao thức hiện tại còn đáp ứng **threat model, lifecycle, interoperability và yêu cầu mới** hay không; từ đó lập migration có phiên bản, approval và tránh downgrade.

## 24. Kết luận

**Policy review là vòng phản hồi biến cryptographic policy từ văn bản thành cơ chế quản trị có thể kiểm chứng.** Để làm tốt, cần rà soát cả **tính phù hợp của yêu cầu, tính đúng đắn của triển khai và hiệu lực vận hành**, với bằng chứng đủ nguồn, phạm vi, thời điểm và độ tin cậy.

Trong hệ thống Java quản lý khóa, review phải đi qua **key inventory, owner/custodian, KMS/HSM attributes và IAM grants, DEK/KEK cùng envelope encryption, AES-GCM nonce/AAD/tag, chữ ký số và trust, password KDF, TLS/key establishment, key lifecycle, rotation, revocation, backup/restore, ngoại lệ và audit**. Một số kiểm tra có thể tự động hóa từ metadata; những quyết định **rủi ro, threat model, ứng phó sự cố, hủy khóa và approval** cần trách nhiệm con người rõ ràng.

**Một chính sách mật mã chỉ còn giá trị khi tổ chức biết chính sách nào đang áp dụng, có thể chứng minh hệ thống thực sự tuân thủ, nhận ra sai lệch kịp thời và xác minh độc lập rằng rủi ro đã được xử lý đúng cách.**
