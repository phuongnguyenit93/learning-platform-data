# Key custodian: người giám hộ khóa mật mã trong hệ thống key inventory

## 1. Vì sao cần key custodian?

Giả sử một doanh nghiệp có ba loại khóa quan trọng:

- **KEK** (*Key Encryption Key*) trong HSM/KMS dùng bảo vệ nhiều **DEK** của dữ liệu khách hàng.
- **Private signing key** dùng ký bản phát hành ứng dụng Java và thông điệp đối tác.
- **Khóa HMAC** dùng xác thực sự kiện giữa các dịch vụ.

Từng khóa có mã định danh và thuật toán rõ ràng, nhưng không ai trả lời chính xác được:

> Ai chịu trách nhiệm giám hộ khóa? Ai được phê duyệt việc cấp quyền, thay khóa, xuất/nhập hay hủy khóa? Nếu người quản trị nghỉ việc, nhà cung cấp KMS gặp sự cố hoặc cần khôi phục bản sao, ai có quyền và quy trình nào được phép thực hiện?

Những lỗ hổng này không nằm ở AES, HMAC hay RSA. Chúng là **lỗ hổng quản trị và trách nhiệm đối với vật liệu khóa**.

**Key custodian** là **người, nhóm hoặc vai trò được giao trách nhiệm giữ gìn sự kiểm soát an toàn đối với một khóa mật mã hoặc phương tiện bảo vệ khóa**, theo chính sách tổ chức. Trong nhiều hệ thống, custodian chịu trách nhiệm thực thi hoặc phối hợp các hoạt động **tiếp nhận, bảo quản, kiểm soát truy cập, sao lưu/khôi phục, bàn giao, đối soát, xử lý sự cố và hủy khóa**, nhưng **không mặc nhiên** là người sở hữu dữ liệu, người phê duyệt mọi hành động hay người được phép dùng khóa để giải mã/ký.

Điểm mấu chốt:

> **Custody là trách nhiệm bảo quản và kiểm soát, không tự đồng nghĩa quyền biết raw key, quyền sử dụng mọi thao tác mật mã hoặc quyền quyết định mục đích của khóa.**

Trong **key inventory** (sổ kiểm kê khóa), trường **custodian** giúp gắn một khóa với trách nhiệm vận hành cụ thể. Nếu không có trách nhiệm này, các hoạt động rotation, thu hồi, kiểm toán hoặc khôi phục thường bị đứt gãy khi có thay đổi nhân sự hay môi trường triển khai.

### Một tình huống cụ thể

Một service đã bị chiếm quyền và có khả năng gọi **KMS Decrypt** trên tất cả DEK. Dù KEK trong HSM là **non-exportable**, attacker vẫn có thể yêu cầu giải mã qua API nếu quyền được cấp quá rộng.

Trong tình huống này, custodian phải giúp bảo đảm **key policy, grant, danh tính workload, cảnh báo và quy trình thu hồi** được kiểm soát. Chỉ phát biểu “khóa nằm trong HSM nên đã an toàn” là thiếu một nửa bức tranh.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **key custodian** và phân biệt với **key owner, key administrator, key user, security officer và auditor**.
2. Xác định những trường **inventory metadata** cần có để truy vết trách nhiệm giám hộ mà **không lưu secret trong inventory**.
3. Hiểu **custody model**: khóa trong HSM/KMS, kho bí mật, offline storage, bản backup hoặc thiết bị phần cứng.
4. Áp dụng **least privilege, separation of duties, dual control, split knowledge và quorum** phù hợp.
5. Thiết kế quy trình **đăng ký custodian, tiếp nhận, thay người phụ trách, sử dụng, sao lưu, rotation, thu hồi và hủy khóa**.
6. Phân biệt **giám hộ key material** với **phê duyệt sử dụng key** và **quyền nghiệp vụ trên dữ liệu**.
7. Nhận diện các sự cố: custodian nghỉ việc, mất recovery shares, lộ backup, lạm dụng quyền KMS, key không có owner, xóa khóa trước thời hạn.
8. Đọc ví dụ **Java 17** mô hình hóa key inventory và kiểm soát quyền trước thao tác; hiểu tại sao logic ứng dụng không thay IAM/KMS/HSM thật.
9. Đề xuất các bằng chứng kiểm toán, chỉ số và quy trình ứng phó cho hệ thống quản lý khóa.

## 2. Key custodian nằm ở đâu trong key inventory?

**Key inventory** là danh mục có kiểm soát các khóa tồn tại trong hệ thống: chúng dùng vào việc gì, do ai chịu trách nhiệm, được giữ ở đâu, đang ở phiên bản/trạng thái nào và còn phụ thuộc dữ liệu nào.

Một bản ghi inventory thường **chỉ chứa metadata**, không phải byte bí mật của khóa.

~~~text
Key inventory
  ├─ Key ID / version
  ├─ Key type / algorithm / purpose
  ├─ Owner (người chịu trách nhiệm nghiệp vụ)
  ├─ Custodian (bộ phận chịu trách nhiệm giám hộ)
  ├─ Storage / KMS-HSM reference
  ├─ Access policy / principals / key usage
  ├─ Lifecycle state / cryptoperiod
  ├─ Rotation / revocation / destruction policy
  ├─ Backup / recovery dependencies
  └─ Audit evidence / approval references
~~~

### 2.1. Custodian và key owner khác nhau như thế nào?

**Key owner** chịu trách nhiệm xác định **mục đích, rủi ro, dữ liệu và chính sách** của khóa. Ví dụ, bộ phận thanh toán xác định một signing key chỉ được ký **payment settlement manifest**.

**Key custodian** chịu trách nhiệm bảo vệ và vận hành khóa theo chính sách đã được phê duyệt. Ví dụ, đội quản lý HSM bảo đảm private key nằm trong đúng partition, không xuất được, chỉ principal đã cấp phép gọi Sign, có key recovery policy và audit.

| Nội dung | Key owner | Key custodian |
| --- | --- | --- |
| Xác định khóa bảo vệ dữ liệu/nghiệp vụ nào | **Chịu trách nhiệm chính** | Tư vấn khả năng kỹ thuật |
| Chấp nhận rủi ro và phê duyệt mục đích/cryptoperiod | Theo chính sách tổ chức | Thực thi và báo cáo |
| Giữ vật liệu khóa hoặc giám hộ ranh giới lưu trữ | Không mặc nhiên | **Trách nhiệm trọng tâm** |
| Đề xuất/thi hành backup, recovery và rotation | Phê duyệt yêu cầu/rủi ro | Tổ chức thực hiện theo quyền được giao |
| Cấp quyền Decrypt/Sign/Unwrap | Phê duyệt quyền nghiệp vụ theo quy trình | Áp đặt policy/grant sau phê duyệt |
| Khôi phục khi mất khóa | Quyết định yêu cầu và tác động nghiệp vụ | Điều phối thao tác/đối soát theo runbook |
| Trả lời audit về ownership | Có | Có, đối với custody và bằng chứng vận hành |

**Không có quy tắc toàn cầu yêu cầu hai vai trò luôn là hai con người khác nhau.** Nhưng với khóa rủi ro cao, **tách trách nhiệm** giữa người phê duyệt và người có khả năng thao tác kỹ thuật giúp giảm nguy cơ một cá nhân tự phê duyệt, thực hiện và che giấu hành động.

### 2.2. Custodian khác key administrator, key user và auditor

| Vai trò | Trách nhiệm thường gặp | Không nên tự có |
| --- | --- | --- |
| **Key owner** | Mục tiêu bảo vệ, data classification, policy, chấp thuận thay đổi | Mặc định xuất private key/DEK |
| **Key custodian** | Bảo quản, kiểm soát quy trình custody, bàn giao, backup/recovery, đối soát | Quyền tự quyết định mọi mục đích của khóa |
| **Key administrator** | Thực hiện thao tác quản trị theo ticket/approval: create, grant, rotate, disable | Quyền giải mã toàn bộ dữ liệu chỉ vì là admin |
| **Key user / workload** | Thực hiện **Encrypt, Decrypt, Sign, Verify, MAC, Wrap** trong phạm vi ứng dụng | Quyền đổi key policy/hủy khóa |
| **Security officer / approver** | Phê duyệt thay đổi nhạy cảm, giám sát tuân thủ và phân tách nhiệm vụ | Raw key material nếu không cần |
| **Auditor** | Đối soát inventory với system log, policy, bằng chứng lifecycle | Quyền Sign/Decrypt/Unwrap hoặc sửa audit log |
| **Recovery operator** | Phục hồi theo quy trình khẩn cấp đã duyệt | Quyền thường trực vô hạn với mọi khóa |

Một cá nhân có thể kiêm vai trò ở tổ chức nhỏ, nhưng quyền **phê duyệt, thực thi, xác nhận độc lập và xóa bằng chứng** không nên gom vào một tài khoản khi rủi ro yêu cầu kiểm soát chéo.

### 2.3. Custodian là cá nhân hay nhóm?

Trong inventory, nên ghi rõ:

- **Custodian team/role** chịu trách nhiệm lâu dài, ví dụ \`crypto-operations\`.
- **Primary custodian** và **backup custodian** được chỉ định trong hệ thống phân quyền (có thể thay đổi theo nhân sự).
- **Manager/escalation path**, thời hạn trực hoặc cơ chế chuyển giao.
- **Ticket/approval reference** cho các thay đổi custody.

Không nên chỉ ghi một địa chỉ email cá nhân rồi xem như đã có khả năng vận hành bền vững. Người nghỉ việc, đổi nhóm hoặc hết quyền truy cập cần được **cập nhật inventory và IAM cùng lúc**.

Thông tin liên hệ có thể nằm trong hệ thống quản trị nhân sự/ticket riêng; inventory chỉ cần tham chiếu đủ để truy vết. Hạn chế nhân bản dữ liệu cá nhân không cần thiết.

## 3. Các mô hình custody của khóa

“Giữ khóa” có nhiều cấp độ. Không phải mọi custodian đều **nhìn thấy plaintext key**.

### 3.1. KMS/HSM managed custody

Đây là mô hình quan trọng trong hệ thống doanh nghiệp:

- **KMS/HSM** giữ hoặc quản lý **KEK, private signing key, HMAC key** và các khóa khác theo khả năng của nền tảng.
- Key có thể được đánh dấu **non-exportable** ở mức tính năng hoặc chính sách.
- **Custodian** duy trì trạng thái, policy, grants, quy trình backup/recovery và xử lý sự cố.
- **Workload** được cấp quyền gọi các API cụ thể, ví dụ GenerateDataKey, Encrypt, Decrypt, Sign, VerifyMac, Wrap/Unwrap.
- **Audit** ghi key ID, principal, action, kết quả và policy change.

**Non-exportable không có nghĩa không thể bị lạm dụng.** Nếu principal có quyền Sign rộng, nó vẫn có thể yêu cầu ký nội dung giả. Nếu có quyền Decrypt/Unwrap rộng, nó có thể nhận plaintext hoặc DEK thông qua API dù không xuất được **KEK**.

### 3.2. Custody trong software keystore hoặc secret manager

Một khóa có thể được lưu trong **keystore, secret manager hoặc môi trường runtime** thay vì HSM.

Rủi ro tăng khi:

- Khóa được export dưới dạng \`byte[]\`, PEM private key hoặc environment variable.
- Secret được ghi vào crash dump, log, file cấu hình hoặc image container.
- Backup sao chép khóa rõ mà không có ranh giới mã hóa/ủy quyền độc lập.
- Một tài khoản CI/CD có thể đọc tất cả bí mật của production.

Custodian cần kiểm soát **secret source, quyền đọc, luồng phân phối, log/backup, retention và rotation**, không chỉ nơi lưu ở trạng thái nghỉ.

### 3.3. Offline hoặc physical custody

Với một số tổ chức, root keys, HSM recovery materials hoặc emergency shares được bảo quản **offline**:

- Thiết bị/hardware token trong kho có kiểm soát.
- Recovery shares thuộc các custodian độc lập.
- Bản backup mã hóa, niêm phong hoặc phương tiện vật lý có mã nhận diện.
- Sổ giao nhận, người nhận và người chứng kiến.

Cần tính tới:

- Kiểm soát vào kho, người giữ, tamper evidence.
- Danh sách phương tiện được phép, số seri, thời điểm niêm phong.
- Phân tách địa điểm để tránh một sự cố phá hủy mọi bản sao.
- Khả năng khôi phục có kiểm chứng, thay vì chỉ tin “có bản backup”.
- Các giới hạn pháp lý/quy định dữ liệu và xuất khẩu khóa nếu áp dụng.

### 3.4. Custody không nên được suy từ tên nhà cung cấp

Một hệ thống dùng “cloud KMS” không tự nói rằng **ai chịu trách nhiệm** từng phần:

| Câu hỏi | Cần xác định rõ |
| --- | --- |
| Ai vận hành phần cứng HSM và hạ tầng? | Có thể là nhà cung cấp dịch vụ |
| Ai được thay IAM grants và key policy? | Nhóm/tài khoản của tổ chức hoặc nhà cung cấp, tùy cấu hình |
| Ai sở hữu rủi ro và quyết định cryptoperiod? | Key owner/security policy của tổ chức |
| Ai quản lý recovery/ticket/đối soát? | Custodian được chỉ định |
| Ai có thể gọi Decrypt/Sign? | Các workload/principal do policy cho phép |
| Ai audit việc sử dụng? | Security/auditor và hệ thống ghi log |

Đừng đưa tên nhà cung cấp vào trường **custodian** rồi bỏ trống trách nhiệm nội bộ. Mô hình trách nhiệm chia sẻ phải được diễn đạt cụ thể trong inventory và quy trình.

## 4. Thiết kế key inventory record có custodian

### 4.1. Dữ liệu cần ghi

Một bản ghi inventory nên đủ để người vận hành trả lời:

**Khóa nào? Dùng làm gì? Thuộc ai? Ai bảo quản? Ở đâu? Ai dùng được? Ở trạng thái nào? Khi nào cần rotate/hủy? Backup nào còn phụ thuộc?**

| Nhóm metadata | Trường minh họa | Vai trò custodian |
| --- | --- | --- |
| **Identity** | key ID, key version, alias, provider resource reference | Đối chiếu đúng vật liệu và phiên bản |
| **Classification** | symmetric/asymmetric/HMAC/root, algorithm, key size | Bảo đảm loại khóa dùng đúng primitive |
| **Business** | service, data classification, environment, tenant scope, purpose | Liên hệ owner và quyền ứng dụng |
| **Governance** | ownerTeam, custodianTeam, backupCustodian, escalation | Không để khóa vô chủ/vô giám hộ |
| **Usage** | allowed operations, principals, grant/policy reference | Giám sát phân quyền tối thiểu |
| **Storage** | HSM/KMS/keystore reference, region/partition, exportability | Bảo vệ nơi lưu và vật liệu khóa |
| **Lifecycle** | creation/activation/expiry, state, rotate date, retirement | Thực hiện chuyển trạng thái đúng lúc |
| **Recovery** | backup reference, recovery policy, quorum, restore test date | Bảo đảm có thể phục hồi hoặc biết rõ không thể |
| **Dependency** | wrapped DEKs, datasets, signing verifiers, certificates | Tránh hủy khóa khi còn dữ liệu phụ thuộc |
| **Evidence** | change ticket, approval IDs, audit log references | Chứng minh thay đổi được cho phép |

Có thể thêm trường **custodyMode** để phân biệt \`HSM_MANAGED\`, \`KMS_MANAGED\`, \`SOFTWARE_KEYSTORE\`, \`OFFLINE_RECOVERY\` hoặc mô hình khác. Danh sách này là **quy ước minh họa**, không phải các giá trị tiêu chuẩn bắt buộc.

### 4.2. Bản ghi inventory minh họa

~~~json
{
  "inventorySchemaVersion": 1,
  "keyId": "billing-kek-prod-v3",
  "keyVersion": "v3",
  "algorithm": "AES-256",
  "keyClass": "KEK",
  "purpose": "wrap-billing-deks",
  "service": "billing",
  "environment": "production",
  "tenantScope": "billing-production",
  "ownerTeam": "billing-platform",
  "custodianTeam": "cryptography-operations",
  "backupCustodianTeam": "security-recovery",
  "custodyMode": "KMS_MANAGED",
  "materialReference": "kms:billing-production/billing-kek-prod-v3",
  "exportable": false,
  "allowedOperations": ["Wrap", "Unwrap"],
  "state": "ACTIVE",
  "activatedAt": "2026-10-01T00:00:00Z",
  "reviewDueAt": "2027-01-01T00:00:00Z",
  "rotationPolicyRef": "key-policy/billing-kek",
  "accessPolicyRef": "iam-policy/billing-key-usage",
  "recoveryPolicyRef": "recovery-plan/billing-prod",
  "lastRestoreTestRef": "change/restore-test-example",
  "lastApprovalRef": "change/key-activation-example"
}
~~~

Tất cả giá trị trong record chỉ là **ví dụ dữ liệu giả định**. Các trường định danh **không phải raw key, password, recovery share hay token**.

**Không lưu trong inventory:**

- AES raw key, KEK/DEK dạng rõ, HMAC secret.
- Private signing key PEM, HSM root secret hoặc recovery share.
- Password, passphrase, pepper hoặc token truy cập.
- Dữ liệu khách hàng hoặc plaintext được bảo vệ bởi key.
- File backup có chứa key material dưới dạng dễ đọc.

Một key ID không phải bí mật mật mã, nhưng vẫn có thể là **thông tin cấu trúc nội bộ**. Áp dụng quyền đọc inventory phù hợp, tránh công khai sơ đồ hạ tầng không cần thiết.

### 4.3. Một khóa có thể có nhiều custodian?

Một số trường hợp có thể cần:

- **Primary custodian:** chịu trách nhiệm chính về khóa.
- **Backup/secondary custodian:** bảo đảm khả năng vận hành khi primary vắng mặt.
- **Separate recovery custodians:** mỗi người giữ một phần recovery theo cơ chế chia sẻ bí mật hoặc nhận nhiệm vụ độc lập.
- **Provider custodian:** phạm vi nhà cung cấp vận hành hạ tầng theo hợp đồng.

Nhưng phải rõ **ai accountable**, ai được giao hành động, ai xác minh độc lập. Nếu nhiều nhóm đều ghi “đồng phụ trách” mà không có người quyết định/escalation, thực chất khóa vẫn có thể trở nên vô chủ.

## 5. Chain of custody: chuỗi trách nhiệm bàn giao khóa

**Chain of custody** là khả năng truy vết khóa hoặc vật liệu khôi phục đã ở dưới sự kiểm soát của chủ thể nào, qua các lần chuyển giao và trong điều kiện nào.

Nó đặc biệt quan trọng đối với:

- Khóa được nhập vào HSM từ nguồn ngoài.
- Root/KEK backup và recovery shares.
- Hardware tokens, smart cards, offline storage.
- Thay key custodian do chuyển bộ phận, nghỉ việc hoặc thay nhà cung cấp.
- Điều tra nghi ngờ truy cập trái phép hoặc mất khóa.

### 5.1. Quy trình tiếp nhận ban đầu

~~~mermaid
flowchart TD
    A["Owner đề nghị đưa khóa vào quản lý"] --> B["Xác định purpose, classification, rủi ro"]
    B --> C["Chỉ định primary và backup custodian"]
    C --> D["Phê duyệt key creation/import theo policy"]
    D --> E["Tạo hoặc import trong ranh giới tin cậy"]
    E --> F["Đối chiếu key ID, usage, exportability, state"]
    F --> G["Ghi inventory + custody/approval evidence"]
    G --> H["Kiểm tra IAM grants, audit và recovery plan"]
    H --> I["Kích hoạt theo phê duyệt"]
~~~

Với khóa **non-exportable** được tạo trong KMS/HSM, custodian thường **không cầm raw key**. Chuỗi custody khi đó là **chuỗi kiểm soát policy và hệ thống**: ai được phép tạo, dùng, thay, xóa khóa, và các bằng chứng từ KMS/IAM/audit.

### 5.2. Quy trình bàn giao custodianship

Khi thay người/nhóm chịu trách nhiệm:

1. Xác định **key ID/version, owner, mục đích, mức độ nhạy cảm và trạng thái**.
2. Owner hoặc người có thẩm quyền phê duyệt **custodian mới** theo quy trình.
3. Đối chiếu **danh sách quyền** và các đường quản trị trong KMS/HSM, secret manager, ticketing, vault và hệ thống recovery.
4. Cấp quyền mới ở mức tối thiểu theo phân quyền; kiểm tra khả năng thực thi đúng runbook.
5. Thu hồi **role, token, physical access, smart card hoặc recovery credential** của custodian cũ khi không còn cần.
6. Đối soát inventory: primary/backup, escalation, location/partition, key policy version, approval reference.
7. Ghi audit ai bàn giao, ai nhận, thời điểm và bằng chứng kiểm tra.
8. Kiểm tra một lần nữa xem **custodian cũ có còn quyền vận hành** qua nhóm IAM kế thừa, service account chia sẻ hoặc token dài hạn không.

**Chỉ đổi tên trường \`custodianTeam\` trong JSON chưa phải bàn giao hoàn tất.** Quyền truy cập thực tế và recovery materials phải chuyển theo cùng quy trình.

### 5.3. Custody log nên ghi gì?

Một bản ghi sự kiện có thể gồm:

~~~json
{
  "eventType": "KEY_CUSTODY_TRANSFER",
  "keyId": "billing-kek-prod-v3",
  "eventTime": "2026-11-28T02:00:00Z",
  "fromRole": "cryptography-operations",
  "toRole": "security-recovery",
  "approvedChangeRef": "change/custody-transfer-example",
  "iamPolicyReviewRef": "audit/policy-review-example",
  "result": "SUCCESS"
}
~~~

Đây là ví dụ cấu trúc sự kiện, không yêu cầu ghi danh tính cá nhân đầy đủ hoặc nội dung khóa. Trong hệ thống thật, sự kiện cần **bằng chứng từ nguồn xác thực**, có độ bền/tính toàn vẹn phù hợp; không coi một bản ghi JSON do bất kỳ client nào tự gửi là audit đã đáng tin.

### 5.4. Kiểm tra định kỳ custody

Custodian hoặc auditor nên đối chiếu:

- Key inventory có khớp khóa thực tế trong KMS/HSM không?
- Có khóa **orphan** không có owner/custodian?
- Có key đã disabled/destroyed nhưng inventory vẫn ACTIVE?
- Có key mới được tạo thủ công ngoài quy trình đăng ký?
- Có IAM grants tạm thời chưa thu hồi?
- Có backup/recovery shares không còn custodian hợp lệ?
- Có key cần rotate hoặc review policy nhưng quá hạn?
- Có người đã nghỉ việc vẫn có quyền console, API hoặc vật lý không?

Việc đối soát không cần phải xuất raw key từ HSM; thường chỉ cần **metadata, access policy, status và audit evidence**.

## 6. Separation of duties, dual control và split knowledge

Đối với khóa rủi ro cao, không nên để một cá nhân có thể **tự đề xuất, tự phê duyệt, tự xuất khóa và xóa dấu vết**.

### 6.1. Separation of duties (SoD)

**Separation of duties** là tách các quyền có khả năng xung đột:

- Owner phê duyệt mục đích và quyền.
- Custodian tổ chức bảo quản và quản trị theo yêu cầu đã được duyệt.
- Workload chỉ gọi đúng crypto operation.
- Auditor kiểm tra bằng chứng mà không sửa key policy/audit log.

Ví dụ, tài khoản dùng để **Sign release** không nên đồng thời có quyền **thay public verification key/trust store của verifier** và **xóa audit log**, nếu có thể thiết kế tách vai trò.

### 6.2. Dual control (kiểm soát hai bên)

**Dual control** thường yêu cầu **hai chủ thể độc lập** tham gia một hoạt động nhạy cảm, như:

- Tạo/import root signing key hoặc KEK cấp cao.
- Phê duyệt thay key policy cho phép export/Decrypt rộng.
- Khôi phục HSM từ backup hoặc kích hoạt recovery.
- Hủy vĩnh viễn khóa còn phụ thuộc dữ liệu.
- Chuyển giao custody ngoài quy trình thông thường.

Ví dụ một thay đổi cần **owner approval + custodian execution**, và có thể có security approval thứ hai theo mức độ rủi ro.

**Hai người cùng biết một password chung rồi lần lượt nhập không mặc nhiên là dual control có hiệu lực.** Phải bảo đảm tính độc lập của approval, khó vượt qua quy trình và có log kiểm tra.

### 6.3. Split knowledge và quorum

**Split knowledge** chia bí mật hoặc quyền khôi phục thành các phần mà mỗi bên chỉ có **một phần không đủ** để tái tạo secret. Một cơ chế **threshold secret sharing** có thể yêu cầu **m trong n** phần hợp lệ để khôi phục.

~~~text
Recovery material cấp cao
       |
   Secret-sharing theo thiết kế được phê duyệt
       |
       +--> Share 1: Custodian A
       +--> Share 2: Custodian B
       +--> Share 3: Custodian C

Chính sách ví dụ: cần 2 trong 3 share mới có thể phục hồi.
~~~

**Quorum** cũng có thể được áp dụng dưới dạng **đa chữ ký/phê duyệt** mà không xuất hoặc phân chia raw key. Hai mô hình này **không đồng nghĩa**:

| Cơ chế | Đối tượng được chia/tách | Cần lưu ý |
| --- | --- | --- |
| **Dual approval** | Quyền phê duyệt một hành động | Phải kiểm tra độc lập và chống cùng tài khoản tự duyệt |
| **Quorum of operators** | Quyền kích hoạt thao tác nhạy cảm | Có thể do HSM/approval system hỗ trợ, tùy provider |
| **Secret sharing (m-of-n)** | Vật liệu khôi phục bí mật | Cần thuật toán chuẩn, lưu shares riêng và có kiểm thử |
| **Multi-person physical access** | Quyền tiếp cận thiết bị/phương tiện | Không tự chứng minh raw key không bị sao chép |

**Không tự chia key bằng cách cắt 32 byte thành nhiều đoạn rồi coi đó là một secret-sharing scheme chuẩn.** Việc mất một đoạn có thể làm không thể khôi phục; việc chia cơ học còn thiếu những tính chất mong muốn của lược đồ ngưỡng. Dùng cơ chế chuẩn do HSM/nhà cung cấp hoặc thiết kế được phê duyệt hỗ trợ.

### 6.4. Kiểm soát recovery shares

Nếu dùng recovery shares, custodian phải đảm bảo:

1. Mỗi share được gắn mã định danh, owner, thời gian cấp phát, cách bảo vệ và người nhận.
2. Các share được giữ **độc lập** theo địa điểm/người/quyền truy cập, tránh mọi share cùng nằm trong một vault mà một tài khoản mở được.
3. Có lịch **rotate/replace/revoke** khi custodian nghỉ việc hoặc nghi ngờ share bị lộ.
4. Có quy trình **khôi phục có kiểm soát và kiểm thử định kỳ**.
5. Không chụp ảnh/gửi share qua chat/email/log/clipboard không an toàn.
6. Chỉ ghi metadata và bằng chứng vận hành trong inventory, **không ghi giá trị share**.
7. Có phương án khi một share bị hỏng hoặc không thể truy cập nhưng vẫn trong ngưỡng khôi phục.

### 6.5. Kiểm soát quá mức cũng có rủi ro vận hành

Nếu phục hồi một hệ thống quan trọng cần bốn custodian nhưng chỉ có ba người có thể liên hệ trong kỳ nghỉ, dịch vụ có thể dừng lâu dù khóa chưa bị lộ.

Thiết kế phải cân bằng:

- **Security:** ngăn một người tự ý khôi phục/xuất/hủy khóa.
- **Availability:** có đủ số người/quyền trong tình huống khẩn cấp.
- **Accountability:** ai đã tham gia, ai xác nhận và bằng chứng gì được ghi.
- **Recovery testability:** có thể chứng minh phục hồi thành công mà không làm lộ raw key.

Không nên duy trì một “break-glass master key” không được kiểm kê và không có audit để giải quyết nguy cơ sẵn sàng.

## 7. Key ceremony: custodian làm gì tại những hoạt động nhạy cảm?

**Key ceremony** là một quy trình có chuẩn bị và kiểm soát để tạo, nhập, kích hoạt, sao lưu, phục hồi, chuyển giao hoặc hủy vật liệu khóa có giá trị đặc biệt cao. Không phải mọi khóa DEK ngắn hạn đều cần ceremony thủ công; hãy chọn theo **phân loại khóa và chính sách rủi ro**.

### 7.1. Trước ceremony

- Owner nêu **mục đích, dữ liệu bị ảnh hưởng, thuật toán, key length, lifetime và yêu cầu khôi phục**.
- Custodian xác định **HSM partition, key attributes, exportability, policy và máy/trạm được dùng**.
- Chỉ định **operators, approvers, witnesses** và kiểm tra xung đột vai trò.
- Kiểm tra thiết bị, firmware/hạ tầng theo chính sách và trạng thái audit.
- Chuẩn bị **runbook, ticket, kế hoạch rollback/abort** và cách xử lý khi bước nào đó thất bại.
- Xác nhận có thể ghi **key ID/fingerprint của public key** hoặc metadata mà không ghi raw secret.

### 7.2. Trong ceremony

~~~mermaid
sequenceDiagram
    participant O as Key owner
    participant C as Key custodian
    participant A as Independent approver
    participant H as HSM/KMS
    participant L as Audit log
    O->>A: Yêu cầu tạo/import khóa rủi ro cao
    A-->>C: Approval và phạm vi thao tác
    C->>H: Thực hiện theo runbook đã duyệt
    H-->>C: Key reference + key attributes
    C->>C: Kiểm tra state, exportability, allowed operations
    C->>L: Ghi ticket, key ID, actor, policy và kết quả
    C-->>O: Bàn giao key reference và trạng thái
    Note over O,H: Raw key hoặc recovery shares không đưa vào ticket/log
~~~

Nếu HSM dùng quorum hoặc smart cards, từng operator chỉ thực hiện phần được phân công. Khi thất bại hoặc có bất thường, **dừng và xử lý theo runbook**, không tự bỏ qua kiểm soát hay chuyển raw key qua kênh khác.

### 7.3. Sau ceremony

- Đối chiếu inventory với khóa thực tế ở HSM/KMS.
- Kiểm tra **allowed operations**, IAM grants, cryptoperiod, version và backup/recovery metadata.
- Xác nhận actor không có quyền tạm thời ngoài phạm vi sau khi kết thúc.
- Ghi **evidence references** và người phê duyệt, người thực hiện, người xác nhận độc lập.
- Thông báo owner rằng khóa đã **ready for activation**, không tự dùng khóa trước khi chấp thuận.
- Đánh giá root/KEK/signing key có cần **backup hoặc restore test** theo chính sách không.

**Certificate/verification key có thể công khai**, nhưng việc đưa một public key mới vào trust store phải được kiểm soát như thay đổi bảo mật. Attacker không cần private key thật nếu có thể khiến verifier tin một public key giả do mình tạo.

## 8. Custodian trong sử dụng khóa và IAM

Giai đoạn sử dụng khóa (*Use key*) thường thuộc **workload**. Custodian phải đảm bảo workload chỉ được làm đúng chức năng.

### 8.1. Ma trận quyền minh họa

| Vai trò | Encrypt / GenerateDataKey | Decrypt / Unwrap | Sign | Quản trị key policy | Xem audit |
| --- | --- | --- | --- | --- | --- |
| **Billing writer** | Có trong phạm vi dữ liệu được phép | Không mặc định | Không | Không | Metadata hạn chế |
| **Billing reader** | Không mặc định | Chỉ record/tenant đã cấp quyền | Không | Không | Metadata hạn chế |
| **Release signer** | Không | Không | Chỉ signing key theo purpose và approval | Không | Kết quả Sign của mình |
| **Key custodian** | Không mặc định | Không mặc định | Không mặc định | Theo ticket, quyền hẹp, có SoD | Metadata custody |
| **Key owner** | Không mặc định | Không mặc định | Không mặc định | Phê duyệt chính sách | Trạng thái/rủi ro |
| **Security auditor** | Không | Không | Không | Không | Read-only có kiểm soát |

Một key custodian **không nên nhận Decrypt, GenerateMac, Sign hoặc Export** chỉ vì “phải trông nom khóa”. Nếu nhiệm vụ thật cần thao tác đó, phải có quyền **riêng theo tác vụ, môi trường, thời hạn và approval**.

### 8.2. KMS policy và IAM là hai lớp

- **IAM / identity:** principal nào đang yêu cầu thao tác.
- **Key policy / resource grants:** principal đó được dùng **key ID/version** với action nào.
- **Business authorization:** principal được phép hành động trên **tenant, invoice, user, release manifest** cụ thể hay không.
- **Custody governance:** ai phê duyệt cấp quyền, ai thực thi thay đổi, ai đối soát định kỳ.

**Một lệnh KMS Decrypt thành công không chứng minh người gọi được phép đọc dữ liệu của mọi tenant.** KMS có thể không biết ownership của bản ghi; tầng ứng dụng phải kiểm tra thêm.

### 8.3. KMS encryption context và AAD

Với một số KMS, **encryption context** được cung cấp khi encrypt/decrypt/wrap để ràng buộc với metadata như service, environment hoặc tenant. Đây có thể là cơ sở thêm cho điều kiện truy cập.

~~~json
{
  "service": "billing",
  "environment": "production",
  "tenantId": "tenant-A",
  "purpose": "invoice-dek"
}
~~~

Lưu ý:

- Context **thường không phải bí mật**, có thể xuất hiện trong audit log; không đưa password/token vào.
- Context phải lấy từ **ngữ cảnh đáng tin**, không chỉ từ JSON do client nhập.
- **KMS context bảo vệ lớp wrapped DEK không thay thế AAD của AES-GCM ở tầng dữ liệu**.
- Tính năng và cách ràng buộc context **phụ thuộc provider/key type**, không áp dụng một API tưởng tượng cho mọi KMS.

Custodian phải biết **policy nào sử dụng context** và có thể giải thích luồng **Encrypt/Decrypt/Unwrap** đúng ngữ cảnh khi audit.

### 8.4. Signing key và verification key

Private signing key có thể được bảo vệ trong HSM, trong khi public verification key được phân phối tới client.

Custodian cần quản lý:

- Phạm vi và quyền **Sign** theo purpose.
- Public key/certificate được công bố, **key ID, version, trust source**.
- Quy trình **rotate và revoke signing key** và cập nhật verifier.
- Nguy cơ **key substitution**, khi public verification key bị tráo trong trust store.
- Các bản manifest hoặc token đã ký dưới phiên bản cũ còn cần xác minh lịch sử.

**Key custodian không mặc định là “người ký nghiệp vụ”.** Người được phê duyệt ký thông điệp phải chịu kiểm tra nghiệp vụ trước khi tạo chữ ký; một HSM chỉ đảm bảo khóa được dùng theo API và policy được cấu hình, không kiểm chứng mọi nội dung có hợp lệ về kinh doanh hay không.

### 8.5. Tầng mật mã không thay thế tenant authorization

Ngay cả khi HSM giữ key non-exportable, nếu ứng dụng giải mã dữ liệu dưới KEK chung cho nhiều tenant, custodian cần phối hợp **owner và đội ứng dụng** để kiểm tra:

1. Principal xác thực đúng.
2. Tenant/resource được phân quyền.
3. Key ID và KMS context được chọn đúng.
4. AAD của AES-GCM có ràng buộc record/tenant khi phù hợp.
5. Không sử dụng dữ liệu trước khi xác minh authentication tag.
6. Audit phản ánh thao tác và đối tượng, không làm lộ secret.

Một custodian chỉ quan sát số lượng calls KMS mà không đối soát **purpose và business policy** sẽ bỏ qua nhiều tình huống key misuse.

## 9. Backup, escrow và khả năng khôi phục

### 9.1. Backup key material không giống backup dữ liệu

Một hệ thống có backup ciphertext đầy đủ nhưng **mất KEK/DEK cần thiết** có thể không thể khôi phục plaintext. Custodian phải quản lý **dependencies** giữa khóa và dữ liệu.

| Thành phần | Cần giữ để phục hồi? | Rủi ro nếu thiếu |
| --- | --- | --- |
| **Ciphertext + tag** | Có | Mất nội dung đã mã hóa |
| **Data nonce/IV và AAD/schema metadata** | Có khi cơ chế yêu cầu | Không giải mã/xác thực đúng |
| **Wrapped DEK** | Có trong envelope encryption | Không còn đường mở DEK |
| **KEK/key version** | Có nếu wrapped DEK phụ thuộc | Mất khả năng unwrap |
| **KMS encryption context** | Cần tái tạo chính xác theo API | KMS từ chối giải bọc |
| **Backup/recovery material của khóa** | Tùy custody model | Có thể không thể tái lập khóa cần thiết |
| **Trust/certificate evidence cho chữ ký** | Có thể cần với hồ sơ dài hạn | Không xác minh được danh tính/trạng thái khi ký |
| **Approval/runbook references** | Có ích để phục hồi có kiểm soát | Không truy vết được thao tác khẩn cấp |

**Key backup không đồng nghĩa export raw key.** Nhiều nền tảng cung cấp backup/replication trong ranh giới quản lý hoặc có hạn chế rất cụ thể. Một key non-exportable có thể không thể sao lưu bằng cách người dùng tự lấy byte; đừng tự ý đổi exportability để backup.

### 9.2. Escrow và recovery phải có chính sách

**Key escrow** là mô hình một chủ thể/điểm tin cậy được giữ khả năng khôi phục hoặc truy cập khóa theo điều kiện quy định. Không phải hệ thống nào cũng chấp nhận escrow, nhất là khi mô hình **zero-knowledge** yêu cầu nhà cung cấp không thể giải mã dữ liệu.

Trước khi thiết kế recovery, owner/custodian phải thống nhất:

- Ai có quyền khởi tạo recovery và ai phê duyệt?
- Recovery có cần quorum không?
- Recovery materials nằm ở đâu, được bảo vệ bằng gì?
- Có giữ được tính bí mật tenant hoặc ranh giới pháp lý không?
- Mất một custodian hoặc một site có làm không thể khôi phục không?
- Các bản sao backup/escrow tồn tại bao lâu và bị hủy theo quy tắc nào?
- Có thể thu hồi đường recovery cũ khi nghi bị lộ không?

Không tạo một **master password** nằm trong source code cho phép mở mọi DEK mà không được kiểm kê và kiểm soát.

### 9.3. Restore test cần kiểm tra cả khóa

Một bài kiểm tra khôi phục thực tế phải xác minh:

1. Tài nguyên backup được lấy từ đúng phiên bản/kho.
2. KMS/HSM key ID và state có sẵn theo chính sách.
3. Wrapped DEK được unwrap bằng **đúng KEK và context**.
4. Ciphertext được giải mã với đúng nonce, tag và AAD.
5. Dữ liệu khôi phục đúng nội dung/metadata và không truy cập nhầm tenant.
6. Các recovery operations được audit.
7. Những quyền tạm thời dùng trong restore được thu hồi sau diễn tập.

**Hash của file backup khớp không chứng minh có thể giải mã được nó.** Hash chỉ cho biết byte backup không khác bản tham chiếu; còn phải có khóa và ngữ cảnh xác thực hợp lệ.

## 10. Rotation, thu hồi và hủy: custodian phải làm gì?

### 10.1. Rotation là nhiều quy trình khác nhau

| Loại khóa | Rotation thường tác động | Vai trò custodian |
| --- | --- | --- |
| **KEK** | Thay khóa dùng wrap/unwrap DEK; có thể cần rewrap | Theo dõi version, grants, phụ thuộc backup, thực hiện theo approval |
| **DEK** | Tạo DEK mới, có thể re-encrypt dữ liệu | Hợp tác owner/ứng dụng, theo dõi key usage và migration |
| **Private signing key** | Chuyển signer sang key mới; công bố public verification key mới | Kiểm soát trust distribution, chồng lấp, thu hồi key cũ |
| **HMAC key** | GenerateMac bằng key mới; verify key cũ có giới hạn | Quản lý key IDs, cửa sổ xác minh, chống replay |
| **Root/IKM** | Ảnh hưởng nhiều derived keys | Kiểm kê blast radius, kế hoạch di chuyển theo domain |
| **TLS certificate/signing credential** | Xác thực kết nối tương lai | Phối hợp trust/cert lifecycle, không nhầm với DEK database |

Đừng yêu cầu “rotate tất cả khóa” mà không biết khóa nào có **state, usage, dependencies và phương án migration** khác nhau.

### 10.2. Rewrap khác re-encrypt

~~~text
Dữ liệu cũ:
  plaintext --DEK-v1--> ciphertext-v1
  DEK-v1 --KEK-v1--> wrapped-DEK-v1

Chỉ rewrap:
  DEK-v1 --KEK-v2--> wrapped-DEK-v2
  ciphertext-v1 vẫn có thể giữ nguyên

Re-encrypt:
  plaintext --DEK-v2 + nonce mới--> ciphertext-v2
  DEK-v2 --KEK-v2--> wrapped-DEK-v2
~~~

Custodian có trách nhiệm bảo đảm **đường sử dụng khóa cũ không bị xóa quá sớm** khi dữ liệu/backups còn phụ thuộc, nhưng cũng không giữ quyền Encrypt/Sign cũ vô hạn khi chính sách đã ngừng cho tạo dữ liệu mới.

Một số tổ chức thiết kế trạng thái **decrypt-only/verify-only** trong tầng policy cho khóa cũ. Khả năng native của KMS/HSM có thể khác nhau; cần ánh xạ đúng.

### 10.3. Thu hồi khi nghi khóa bị lộ

Phải phân biệt:

- **Key material compromise:** attacker lấy được raw DEK/KEK/HMAC/private key.
- **Key usage compromise:** attacker có quyền gọi Decrypt/Sign/Unwrap qua API.
- **Custodian account compromise:** attacker có thể thay grants/policy/rotation/recovery.
- **Recovery share compromise:** một phần hoặc đủ phần phục hồi bị lộ.
- **Trust compromise:** public verification key hoặc trust anchor bị tráo.

Mỗi trường hợp cần kế hoạch khác nhau. Việc khóa **non-exportable** không loại bỏ nguy cơ **lộ quyền sử dụng**.

### 10.4. Hủy khóa là thao tác có thể không đảo ngược

Trước khi destroy hoặc schedule deletion:

1. Owner xác nhận **retention và nhu cầu khôi phục** đã hoàn tất.
2. Custodian kiểm kê mọi **wrapped DEK, ciphertext, backup và key version** còn phụ thuộc.
3. Auditor hoặc approver độc lập kiểm tra bằng chứng.
4. Đảm bảo key đã ngừng dùng cho dữ liệu/chữ ký mới.
5. Đối soát migration/rewrap/re-encrypt và restore test khi thích hợp.
6. Thực hiện theo policy về **duyệt xóa, thời gian chờ, quorum, retention**.
7. Ghi nhật ký kết quả và cập nhật inventory.
8. Xem xét các bản sao recovery materials có còn phải hủy riêng hay không.

Không hủy KEK chỉ vì **ứng dụng đã có KEK mới**. Backup nhiều năm trước vẫn có thể chứa DEK được bọc bằng KEK cũ.

## 11. Ví dụ Java 17: inventory và policy gate trước khi dùng khóa

Ví dụ này mô hình hóa **key custodian như một vai trò giám hộ và thực thi thay đổi có phê duyệt**. Nó không chứa bất kỳ **raw key** nào và không yêu cầu SDK KMS cụ thể.

Mục tiêu là chứng minh:

- **Metadata của khóa** có owner, custodian, purpose, tenant scope, state và allowed operations.
- **Key custodian** có thể được phép **Rotate** sau approval, nhưng không mặc định được phép Decrypt dữ liệu.
- **Application writer/reader** có quyền thao tác khác nhau theo key state và tenant.
- **Auditor** có thể xem metadata nhưng không thể thực hiện crypto operation.
- **Export** bị từ chối với key được khai báo non-exportable.

> **Giả định then chốt:** \`Principal\` và \`ApprovalEvidence\` trong ví dụ **đã được xác thực từ hệ thống identity/approval đáng tin**. Không được lấy role hoặc approval từ JSON do client tự khai rồi tin là thật. Trong production, phải thực thi chính sách tại **IAM/KMS/HSM** cùng với business authorization; một phép kiểm tra Java bên ngoài KMS không thể tự khóa một credential có quyền gọi KMS trực tiếp.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class KeyCustodianPolicyDemo {

    enum Role {
        KEY_OWNER, KEY_CUSTODIAN,
        APP_WRITER, APP_READER, SECURITY_AUDITOR
    }

    enum Operation {
        ENCRYPT, DECRYPT, ROTATE, DISABLE, EXPORT
    }

    enum State {
        ACTIVE, READ_ONLY, SUSPENDED, DESTROYED
    }

    record Principal(
            String id, Role role, String tenant, boolean authenticated) {}

    record InventoryKey(
            String keyId, String keyType, String ownerTeam,
            String custodianTeam, String tenantScope,
            State state, Set<Operation> allowedOperations,
            boolean exportable, String kmsReference) {

        InventoryKey {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(keyType);
            Objects.requireNonNull(ownerTeam);
            Objects.requireNonNull(custodianTeam);
            Objects.requireNonNull(tenantScope);
            Objects.requireNonNull(state);
            Objects.requireNonNull(kmsReference);
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    // Trong thực tế, approval phải đến từ workflow được xác thực;
    // không lấy object này trực tiếp từ request chưa tin cậy.
    record ApprovalEvidence(
            String keyId, Operation operation,
            String approvedByPrincipal, Role approvedByRole,
            boolean valid) {}

    private static void deny() {
        throw new SecurityException("Key operation denied");
    }

    private static boolean isApproved(
            InventoryKey key, Principal actor,
            Operation operation, ApprovalEvidence approval) {

        return approval != null
            && approval.valid()
            && key.keyId().equals(approval.keyId())
            && approval.operation() == operation
            && approval.approvedByRole() == Role.KEY_OWNER
            && !actor.id().equals(approval.approvedByPrincipal());
    }

    public static void requireAllowed(
            Principal actor, InventoryKey key,
            Operation operation, ApprovalEvidence approval) {

        Objects.requireNonNull(actor);
        Objects.requireNonNull(key);
        Objects.requireNonNull(operation);

        if (!actor.authenticated()
                || actor.id() == null || actor.id().isBlank()) {
            deny();
        }

        // Khóa non-exportable không được xuất vật liệu từ policy demo.
        if (operation == Operation.EXPORT && !key.exportable()) {
            deny();
        }

        if (!key.allowedOperations().contains(operation)
                || key.state() == State.DESTROYED
                || key.state() == State.SUSPENDED) {
            deny();
        }

        switch (operation) {
            case ENCRYPT -> {
                if (key.state() != State.ACTIVE
                        || actor.role() != Role.APP_WRITER
                        || !key.tenantScope().equals(actor.tenant())) {
                    deny();
                }
            }

            case DECRYPT -> {
                if (actor.role() != Role.APP_READER
                        || !key.tenantScope().equals(actor.tenant())) {
                    deny();
                }
                // READ_ONLY chỉ cho phép dùng để đọc dữ liệu cũ.
                if (key.state() != State.ACTIVE
                        && key.state() != State.READ_ONLY) {
                    deny();
                }
            }

            case ROTATE, DISABLE -> {
                if (actor.role() != Role.KEY_CUSTODIAN
                        || !isApproved(key, actor, operation, approval)) {
                    deny();
                }
            }

            case EXPORT -> deny(); // Demo cấm mọi thao tác export.
        }
    }

    private static void test(
            String name, Principal actor, InventoryKey key,
            Operation action, ApprovalEvidence approval) {

        try {
            requireAllowed(actor, key, action, approval);
            System.out.println(name + ": ALLOWED");
        } catch (SecurityException ex) {
            System.out.println(name + ": DENIED");
        }
    }

    public static void main(String[] args) {
        InventoryKey key = new InventoryKey(
            "billing-dek-scope-v3",
            "AES-256-GCM data key reference",
            "billing-platform",
            "crypto-operations",
            "tenant-A",
            State.ACTIVE,
            EnumSet.of(
                Operation.ENCRYPT, Operation.DECRYPT,
                Operation.ROTATE, Operation.DISABLE),
            false,
            "kms:billing-prod/key-reference"
        );

        Principal writer = new Principal(
            "billing-writer", Role.APP_WRITER, "tenant-A", true);
        Principal readerB = new Principal(
            "billing-reader-b", Role.APP_READER, "tenant-B", true);
        Principal custodian = new Principal(
            "crypto-operator", Role.KEY_CUSTODIAN, "ops", true);
        Principal auditor = new Principal(
            "security-auditor", Role.SECURITY_AUDITOR, "ops", true);

        ApprovalEvidence trustedApproval = new ApprovalEvidence(
            key.keyId(), Operation.ROTATE,
            "billing-owner", Role.KEY_OWNER, true);

        test("Writer encrypt", writer, key,
            Operation.ENCRYPT, null);
        test("Other tenant decrypt", readerB, key,
            Operation.DECRYPT, null);
        test("Custodian decrypt", custodian, key,
            Operation.DECRYPT, null);
        test("Custodian rotate without approval", custodian, key,
            Operation.ROTATE, null);
        test("Custodian rotate approved", custodian, key,
            Operation.ROTATE, trustedApproval);
        test("Auditor export", auditor, key,
            Operation.EXPORT, null);
    }
}
~~~

Kết quả dự kiến:

~~~text
Writer encrypt: ALLOWED
Other tenant decrypt: DENIED
Custodian decrypt: DENIED
Custodian rotate without approval: DENIED
Custodian rotate approved: ALLOWED
Auditor export: DENIED
~~~

### 11.1. Code thể hiện điều gì?

1. **Inventory metadata không chứa secret**: \`kmsReference\` chỉ là một định danh tham chiếu.
2. **Owner và custodian là hai vai trò**: owner có thể phê duyệt, custodian thực thi rotation nếu có approval độc lập.
3. **Role custodian không cho phép Decrypt**: quản trị an toàn khóa khác quyền đọc dữ liệu.
4. **Tenant isolation**: reader tenant B không dùng key của tenant A.
5. **Key state**: \`READ_ONLY\` chỉ cho phép Decrypt theo policy demo; không Encrypt mới.
6. **Non-exportable**: export bị chặn trong policy; production còn phải cấu hình HSM/KMS thật sự không cho xuất khóa.
7. **Fail closed**: mặc định từ chối nếu chưa có điều kiện đủ.
8. **Metadata bất biến ở cấp record**: \`Set.copyOf\` giảm nguy cơ caller sửa allowed operations sau khi tạo đối tượng.

### 11.2. Giới hạn bắt buộc ghi nhớ

- \`ApprovalEvidence.valid\` chỉ là **cờ mô phỏng**. Trong production phải có **approval artifact được xác minh**, gắn actor, key, operation, thời hạn, ticket, trạng thái sử dụng và chống replay; không tin \`valid=true\` do caller gửi.
- Ví dụ không nối với **KMS SDK** và không chặn ai đã có credential KMS riêng gọi trực tiếp API. Các kiểm tra thực tế phải được **củng cố bằng IAM/key policy/grants**.
- Ví dụ không có **authorization theo invoice ID**, context/AAD, quota, rate limit hoặc cơ chế phân quyền thực của nhà cung cấp.
- \`READ_ONLY\` là trạng thái **tầng ứng dụng minh họa**, không phải trạng thái native chung của mọi KMS.
- Demo không thực hiện rotation thật, không cập nhật inventory và không phát audit record đáng tin.
- Demo không phân biệt key version và từng thao tác crypto chi tiết; phải mở rộng theo use case thực và tránh dùng chuỗi key ID từ input chưa tin cậy để truy cập khóa khác.

Không dùng \`KeyCustodianPolicyDemo\` như một **thư viện bảo mật production**. Nó chỉ minh họa những điều kiện nên xuất hiện trước khi hệ thống gọi API KMS/HSM.

## 12. Audit và bằng chứng kiểm soát custody

Một custodian tốt phải có khả năng giải thích **đã làm gì, theo phê duyệt nào, trên khóa nào, khi nào và trong điều kiện ra sao**.

### 12.1. Tối thiểu nên audit những sự kiện nào?

| Nhóm sự kiện | Ví dụ |
| --- | --- |
| **Key registration** | Key được tạo/import, ai phê duyệt, ai giám hộ |
| **Custody assignment/transfer** | Chỉ định/thay primary, backup và recovery custodian |
| **Access change** | Tạo/sửa grant, role, policy, service principal |
| **Crypto use** | GenerateDataKey, Encrypt, Decrypt, Sign, VerifyMac, Unwrap |
| **Lifecycle change** | Enable/Disable, rotate, retire, schedule deletion, destroy |
| **Recovery** | Bắt đầu, phê duyệt, quorum, restore test, kết quả |
| **Incident** | AccessDenied bất thường, usage anomaly, nghi lộ key/credential |
| **Inventory reconciliation** | Khóa thiếu metadata, orphan, trạng thái thực tế sai inventory |

Log thường nên chứa **timestamp, key ID/version, principal, action, policy/approval reference, request ID, kết quả và metadata tối thiểu cần thiết**.

**Không log** raw key, DEK/KEK rõ, private signing key, HMAC secret, recovery shares, password, token hay plaintext nhạy cảm. KMS encryption context có thể xuất hiện trong audit; tránh chứa dữ liệu mật trong context.

### 12.2. Audit log cũng cần custodian và integrity

Nếu attacker có quyền Decrypt hoặc thay key policy và đồng thời xóa log, hệ thống khó điều tra được phạm vi thiệt hại. Cần:

- Đường ghi log riêng hoặc kho audit có chính sách bảo vệ chống sửa/xóa trái phép.
- Tách quyền vận hành khóa với quyền quản trị retention/audit.
- Giới hạn người xem log vì một số metadata vẫn nhạy cảm.
- Đồng bộ thời gian, correlation IDs và retention theo rủi ro/quy định.
- Đối soát log KMS/HSM với **ticket, inventory và IAM changes**.
- Kiểm tra định kỳ quá hạn review/rotation và quyền đã cấp.

**Audit trail không phải cơ chế ngăn chặn trực tiếp**: phải có policy/IAM thực thi trước thao tác. Audit phục vụ phát hiện, truy vết và cải tiến.

### 12.3. Chỉ số quản trị đáng theo dõi

- Tỷ lệ khóa **có owner/custodian hợp lệ** trong tổng số khóa.
- Số khóa **orphan**, không có recovery plan hoặc quá hạn review.
- Số key/grants **khác biệt giữa inventory và KMS/HSM**.
- Số lần custody transfer nhưng quyền custodian cũ chưa được thu hồi.
- Số khóa sắp hết cryptoperiod hoặc đang dùng ngoài chính sách.
- Tỷ lệ **restore test thành công** của những khóa/datasets phải khôi phục.
- Số lần sử dụng **break-glass** và thời gian thu hồi quyền sau đó.
- Số lượng policy/grant changes thiếu approval độc lập.
- Tỷ lệ Key Usage Errors, AccessDenied, Sign/Decrypt bất thường và key import không qua quy trình.

Không đặt mục tiêu “mọi khóa đều có backup” nếu có khóa phiên ephemeral hoặc khóa không thể export/không cần phục hồi. Mục tiêu đúng là **mọi khóa có policy phục hồi/hủy phù hợp với purpose**.

## 13. Kịch bản thực tế: đổi custodian của một KEK production

### Bối cảnh

Một KEK tên **billing-kek-prod-v3** dùng bọc hàng triệu DEK. Primary custodian trước đây thuộc đội CryptoOps; nhân sự phụ trách chuyển sang bộ phận khác. Key owner muốn chuyển custody sang nhóm **Security Platform** mà không làm gián đoạn PaymentService.

### Phương án an toàn

1. **Owner xác nhận phạm vi:** KEK thuộc dữ liệu nào, key state/version, criticality, cryptoperiod và backup.
2. **Chỉ định custodian mới** và người dự phòng; tạo ticket có phê duyệt.
3. **Kiểm kê quyền cũ:** console, KMS key policy, IAM groups, service accounts, break-glass credentials và recovery materials.
4. **Cấp quyền mới có giới hạn:** custodian mới có quyền quản lý cần thiết, **không tự có quyền Unwrap mọi DEK**.
5. **Kiểm tra trạng thái và khôi phục:** xác minh key vẫn non-exportable, DEK cũ còn unwrap được bởi workload được phép, backup/recovery plan còn hợp lệ.
6. **Thu hồi quyền custodian cũ:** xóa nhóm/quyền quản trị, thu hồi token/smart card, thay recovery share nếu chính sách yêu cầu.
7. **Cập nhật inventory:** owner, custodian, backup, escalation, approvalRef, reviewDueAt và ngày bàn giao.
8. **Audit độc lập:** security/auditor đối chiếu policy hiện tại với ticket và hồ sơ inventory.
9. **Theo dõi hậu chuyển giao:** phát hiện lạm dụng Decrypt/Unwrap, AccessDenied bất thường và lỗi vận hành.

~~~mermaid
flowchart TD
    A["Owner phê duyệt chuyển custody"] --> B["Đối soát khóa và các grants hiện tại"]
    B --> C["Cấp quyền custodian mới có giới hạn"]
    C --> D["Kiểm tra state, recovery, khả năng dùng đúng"]
    D --> E["Thu hồi quyền custodian cũ"]
    E --> F["Cập nhật inventory và chain-of-custody evidence"]
    F --> G["Auditor xác nhận độc lập"]
    G --> H["Giám sát thay đổi và đóng ticket"]
~~~

### Những quyết định cần tránh

**Không nên xuất KEK ra file rồi đưa cho nhóm mới** chỉ vì thay custodian. Nếu KEK nằm trong KMS/HSM và không xuất được, chuyển giao nên diễn ra bằng **quyền và trách nhiệm**, không phải sao chép byte khóa.

**Không nên rotate KEK bắt buộc trong mọi lần thay custodian** nếu không có dấu hiệu lộ khóa hoặc chính sách yêu cầu. Đôi khi chuyển quyền quản trị là đủ; tuy nhiên nếu custodian cũ giữ **recovery shares hoặc secret có thể sử dụng ngoài IAM**, cần đánh giá rotate/reconstitute phù hợp.

**Không nên khóa quyền KMS của ứng dụng đọc/ghi** khi chỉ đang thu hồi quyền quản trị custodian cũ, trừ khi chính sách ứng phó sự cố yêu cầu. Phân biệt principal vận hành và principal nghiệp vụ.

## 14. Tình huống sự cố: custodian bị chiếm tài khoản

Một tài khoản của key custodian bị attacker chiếm. Trong log có những yêu cầu thay grants và xem metadata của KEK. Chưa có bằng chứng raw KEK bị export.

### 14.1. Những câu hỏi phải trả lời

- Tài khoản có quyền **thêm IAM grant Decrypt/Sign/Unwrap** không?
- Attacker có thể tạo **service principal** hoặc đổi policy để gián tiếp dùng khóa không?
- Có thể truy cập backup/recovery material, hardware token hoặc vault không?
- Có những thao tác KMS nào đã thực thi, thành công hay bị từ chối?
- Có ứng dụng hoặc tenant nào đã bị thêm quyền không?
- HSM có thực sự non-exportable và policy đã được bảo toàn không?
- Có key/version/alias nào bị đổi dẫn tới ứng dụng dùng sai khóa?
- Có thể xóa/sửa audit logs từ cùng tài khoản không?
- Các phiên đăng nhập/token còn hiệu lực ở hệ thống phụ nào?

### 14.2. Hướng xử lý

1. **Vô hiệu hóa và thu hồi session/credential** của tài khoản nghi vấn.
2. **Đóng băng những thay đổi key policy** rủi ro cao trong phạm vi cần điều tra.
3. Bảo vệ audit log, lịch sử IAM grants và key inventory snapshots.
4. Đối soát permissions/key states/aliases với cấu hình được phê duyệt.
5. Thu hồi grants bất thường; đánh giá **Decrypt/Unwrap/Sign** đã có thể xảy ra.
6. Kiểm tra recovery shares, backup, certificate/trust và các custodian phụ thuộc.
7. Quyết định **rotation/rekey/re-encrypt** dựa trên **loại khóa và mức độ xâm phạm**, không chỉ dựa vào việc raw key có xuất được hay không.
8. Cập nhật custodian/approval chain, tách nhiệm vụ và sửa quy trình bị lợi dụng.
9. Kiểm thử hoạt động, audit và recovery sau xử lý.

**Non-exportable key không loại trừ key usage compromise.** Attacker có thể không biết byte KEK nhưng vẫn dùng chính API để lấy plaintext DEK hoặc tạo chữ ký giả nếu đã có quyền.

### 14.3. Phân biệt rò rỉ vật liệu và rò rỉ quyền

| Sự cố | Có thể ảnh hưởng | Biện pháp điển hình |
| --- | --- | --- |
| **Raw DEK bị lộ** | Dữ liệu mã hóa dưới DEK | Tạo DEK mới/re-encrypt, điều tra các bản sao |
| **Raw KEK bị lộ** | Wrapped DEKs có thể bị giải | Thay KEK, đánh giá thay DEK và dữ liệu liên quan |
| **Quyền KMS Unwrap bị chiếm** | Có thể truy xuất DEK qua API | Thu hồi quyền, phân tích key use logs và dữ liệu đã bị đọc |
| **Private signing key bị lộ** | Tạo chữ ký giả và giả mạo danh tính | Revoke/rotate, thông báo verifier, đánh giá artifacts |
| **Quyền Sign bị chiếm** | Chữ ký giả vẫn tạo được dù key không xuất | Disable grant, điều tra các chữ ký đã tạo |
| **Recovery shares bị lộ** | Có thể tái tạo khóa nếu đủ ngưỡng | Thay shares/khóa theo policy, rà soát mọi custodian |
| **Trust store bị sửa** | Tin public verification key giả | Khôi phục trust, audit các nội dung đã verify |
| **Key bị xóa nhầm** | Mất dữ liệu/khả năng giải mã | Khôi phục theo backup khả dụng hoặc xử lý mất dữ liệu |

## 15. Những sai lầm thường gặp về key custodian

| Sai lầm | Vì sao nguy hiểm? | Phòng ngừa |
| --- | --- | --- |
| **Không ghi custodian trong inventory** | Không ai chịu trách nhiệm recovery/rotation | Bắt buộc custodian và backup theo criticality |
| **Custodian đồng thời có mọi quyền Decrypt/Sign** | Một tài khoản bị chiếm ảnh hưởng nhiều dữ liệu | SoD, least privilege, duty-specific grants |
| **Nhầm owner với custodian** | Quyết định nghiệp vụ và bảo quản không rõ | RACI/trách nhiệm cụ thể |
| **Chỉ ghi tên custodian, không thu hồi IAM của người cũ** | Quyền cũ vẫn tồn tại | Quy trình bàn giao có đối soát thực tế |
| **Lưu raw key/recovery share trong inventory** | Inventory bị lộ đồng nghĩa lộ khóa | Chỉ lưu metadata và references |
| **Coi key non-exportable là không thể bị lạm dụng** | API Decrypt/Sign vẫn có thể bị lợi dụng | Kiểm soát key usage, audit, business authorization |
| **Một custodian giữ toàn bộ recovery shares** | Mất split knowledge/quorum | Giữ riêng độc lập và kiểm tra quyền |
| **Tự chia raw key theo cách ad hoc** | Không có bảo đảm secret-sharing phù hợp | Dùng cơ chế chuẩn được phê duyệt |
| **Không thử restore** | Backup có thể vô dụng khi sự cố | Diễn tập recovery thực tế cả key và ciphertext |
| **Chỉ rotate key, không cập nhật inventory** | Ghi sai version/state/dependencies | Tự động đối soát metadata |
| **Xóa KEK cũ quá sớm** | Backup/dữ liệu cũ không mở được | Dependency mapping và approval trước hủy |
| **Cho client chọn key ID tùy ý** | Lạm dụng key tenant khác | Chọn key theo trusted policy và identity |
| **Không phân biệt KMS policy với quyền nghiệp vụ** | Decrypt hợp lệ nhưng truy cập sai tenant | IAM + authorization + AAD |
| **Cho key admin tự xóa audit logs** | Khó điều tra lạm dụng | Tách quyền audit và kho log chống sửa |
| **Mọi thay đổi đều qua shared admin account** | Mất danh tính thực hiện và SoD | Individual identities, approvals và session logging |
| **Không có kế hoạch khi primary nghỉ việc** | Key trở thành operational single point of failure | Backup custodian và succession process |
| **Coi fingerprint/public key được gửi bất kỳ là đáng tin** | Có thể ký giả và tự cung cấp verification key | Trust store/certificate/JWKS được quản lý |
| **Không kiểm tra cryptoperiod** | Dùng key cũ để tạo ciphertext/chữ ký mới | Lifecycle state và policy tương ứng |

## 16. Checklist triển khai key custodian

1. **Key inventory:** mọi key có ID/version, purpose, algorithm, environment và storage reference chưa?
2. **Ownership:** owner chịu trách nhiệm nghiệp vụ đã được chỉ định và chấp nhận chưa?
3. **Custodianship:** có primary custodian, backup/escalation và tình trạng vai trò còn hiệu lực?
4. **Custody mode:** key ở KMS/HSM, keystore, vault hay offline backup? Ai có quyền với từng ranh giới?
5. **Material vs reference:** inventory không chứa raw key, private key, token hay recovery share?
6. **Key policy:** allowed operations, principals và grants có được ghi nhận/tham chiếu?
7. **Separation of duties:** owner, executor, approver, auditor có xung đột quyền nguy hiểm không?
8. **Dual control:** thao tác root/KEK/signing key rủi ro cao có approval độc lập theo policy?
9. **Split knowledge/quorum:** nếu có recovery shares, mỗi share được giữ độc lập và khôi phục theo cơ chế chuẩn?
10. **Key ceremony:** hoạt động tạo/import/recovery/hủy có runbook, actor, kiểm soát và bằng chứng?
11. **Access review:** quyền của custodian cũ và tài khoản nghỉ việc đã được thu hồi?
12. **Key state:** inventory khớp Enabled/Disabled/PendingDeletion và key version thật?
13. **Cryptoperiod:** có theo dõi activation, expiry, rotate/review deadline, decrypt-only khi thích hợp?
14. **Business authorization:** quyền Decrypt/Sign/Unwrap được kiểm tra cùng tenant/resource và purpose?
15. **Context:** encryption context/KMS grants/AAD có lấy từ nguồn tin cậy, không chỉ metadata do client gửi?
16. **Backup/restore:** có recovery plan, key dependencies và kết quả restore test cho data at rest?
17. **Secret hygiene:** raw DEK/KEK, private key và recovery shares không đi vào log, chat, CI secrets hay inventory?
18. **Monitoring:** có cảnh báo policy change, grant mới, action bất thường, orphan keys và quá hạn review?
19. **Incident response:** đã phân biệt key material compromise với key usage/policy compromise?
20. **Revocation:** có thể tắt nhanh quyền principal, thay key/trust và kiểm tra ảnh hưởng?
21. **Destruction:** có inventory dependency, phê duyệt hủy, retention và xác nhận độc lập?
22. **Handoff:** đổi custodian có cập nhật cả registry, IAM, recovery materials và audit?
23. **Audit integrity:** người quản trị khóa không thể đơn phương xóa bằng chứng lạm dụng?
24. **Testing:** có mô phỏng người nghỉ việc, backup custodian vắng mặt, mất share, sai tenant, restore và rotation?
25. **Governance:** owner/custodian có lịch rà soát chính sách và giải quyết quyền quá rộng?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Key custodian có mặc định được phép Decrypt tất cả dữ liệu dùng khóa mà họ đang quản lý không?

**Đáp án:** Không. Custodian chịu trách nhiệm **bảo quản và kiểm soát**. Quyền Decrypt/Sign/Unwrap phải theo IAM và nhiệm vụ cụ thể, không tự đến từ nhãn custodian.

**Câu 2.** Key owner và key custodian khác nhau ở điều gì quan trọng nhất?

**Đáp án:** Owner chịu trách nhiệm **mục đích, chính sách và rủi ro nghiệp vụ** của khóa; custodian chịu trách nhiệm **giám hộ và vận hành an toàn** theo chính sách đã phê duyệt. Có thể cần tách vai trò để giảm xung đột quyền.

**Câu 3.** Vì sao inventory nên ghi \`kmsReference\` thay vì raw KEK hoặc private signing key?

**Đáp án:** Inventory giúp truy vết quản lý, không phải kho lưu bí mật. Ghi raw key sẽ khiến người có quyền xem inventory có thể dùng hoặc sao chép key material, phá ranh giới bảo vệ KMS/HSM.

**Câu 4.** Một HSM lưu KEK ở dạng non-exportable. Nếu attacker chiếm principal có quyền Unwrap, dữ liệu có an toàn tuyệt đối không?

**Đáp án:** Không. Attacker có thể lạm dụng API Unwrap/Decrypt để lấy DEK hoặc plaintext tùy kiến trúc, dù không bao giờ xuất được KEK. Cần least privilege, giám sát, thu hồi grants và kiểm tra quyền nghiệp vụ.

**Câu 5.** Tại sao thay \`custodianTeam\` trong inventory chưa đủ để hoàn tất bàn giao?

**Đáp án:** Custodian cũ có thể vẫn giữ IAM grants, token, smart cards hoặc recovery shares. Bàn giao chỉ hoàn tất khi cập nhật/truy hồi quyền thực tế, kiểm tra kế hoạch recovery và ghi bằng chứng.

**Câu 6.** Dual control và split knowledge có giống nhau không?

**Đáp án:** Không. Dual control yêu cầu **nhiều chủ thể độc lập cho phép/thực hiện hành động**; split knowledge chia bí mật sao cho một chủ thể không đủ tái tạo toàn bộ. Một thiết kế có thể dùng một hoặc cả hai.

**Câu 7.** Vì sao không nên dùng cách cắt đôi một AES key rồi đưa mỗi nửa cho một người và gọi đó là “threshold secret sharing” chuẩn?

**Đáp án:** Việc cắt byte chỉ chia vật liệu cơ học, thiếu các thuộc tính của một lược đồ ngưỡng được thiết kế/kiểm chứng. Nó cũng tạo rủi ro mất dữ liệu khi một phần không có mặt. Dùng cơ chế được chuẩn hóa hoặc hỗ trợ bởi HSM.

**Câu 8.** Có backup ciphertext và SHA-256 kiểm tra khớp. Nếu đã hủy KEK duy nhất dùng unwrap DEK thì có khôi phục được không?

**Đáp án:** Không bảo đảm, có thể không thể. Hash xác nhận byte backup, không khôi phục được vật liệu khóa đã mất. Cần bảo vệ key dependencies và thử restore cả DEK/KEK/context.

**Câu 9.** Rotation KEK có bắt buộc re-encrypt toàn bộ dữ liệu bằng DEK mới không?

**Đáp án:** Không. Có thể **rewrap cùng DEK** bằng KEK mới mà không đổi ciphertext dữ liệu. Nếu DEK hoặc dữ liệu đã bị lộ, cần đánh giá re-encrypt riêng.

**Câu 10.** Custodian nghỉ việc. Nếu IAM role đã bị xóa nhưng họ còn recovery share offline thì đã thu hồi đầy đủ quyền chưa?

**Đáp án:** Chưa chắc. Phải đánh giá **recovery material**, các shares/quorum còn lại, quy trình thay share hoặc tạo lại khóa nếu chính sách yêu cầu, và đối soát toàn bộ quyền truy cập.

**Câu 11.** Key custodian có thể tự phê duyệt, tự thực hiện hủy root key và xóa audit log không?

**Đáp án:** Không nên trong thiết kế có yêu cầu kiểm soát chéo. Hủy khóa cấp cao thường cần owner/security approval, operator thực thi có giới hạn và bằng chứng audit độc lập; mất root có thể không phục hồi được.

**Câu 12.** Nếu private signing key nằm trong KMS/HSM thì có cần quản lý public verification key và trust store không?

**Đáp án:** Có. Bên nhận cần dùng **public key được xác thực đúng issuer/purpose**. Kẻ tấn công không cần lấy signing key thật nếu có thể thay public verification key mà verifier tin.

**Câu 13.** Key custodian nên dùng metric “tất cả các key có raw backup” hay “mọi key có recovery/destruction policy phù hợp”?

**Đáp án:** Vế thứ hai phù hợp hơn. Một số khóa như ephemeral session keys không nên/không cần backup; nhiều khóa non-exportable không thể sao lưu raw. Quan trọng là rủi ro, khả năng phục hồi và chính sách của **từng loại khóa**.

**Câu 14.** Một principal có quyền dùng DEK nhưng không có quyền đọc hóa đơn của tenant B. KMS Decrypt trả thành công cho bản ghi B. Ứng dụng có được trả plaintext không?

**Đáp án:** Không. KMS/IAM có thể xác thực quyền dùng key nhưng không biết mọi quyền nghiệp vụ của record. Ứng dụng vẫn phải kiểm tra principal–tenant–resource và AAD/context đúng.

**Câu 15.** Vai trò custodian phải làm gì khi phát hiện một signing key đã hết cryptoperiod nhưng vẫn được dùng tạo chữ ký mới?

**Đáp án:** Kiểm tra policy và owner, ngăn tiếp tục Sign trái thời hạn, chuyển signer sang key được phép, đánh giá chữ ký đã phát hành, cập nhật inventory/trust và ghi audit/incident theo mức độ.

**Câu 16.** Khi nghi tài khoản custodian bị chiếm nhưng chưa thấy raw key export, có thể kết luận “không có compromise” không?

**Đáp án:** Không. Attacker có thể đã thay grants, gọi API Sign/Unwrap, sửa trust hoặc chạm vào recovery materials. Cần điều tra **key usage/policy compromise**, không chỉ raw key compromise.

## Kết luận

**Key custodian là vai trò giám hộ và kiểm soát trách nhiệm đối với khóa mật mã**, giúp key inventory trở thành một công cụ vận hành chứ không chỉ là danh sách key IDs. Một khóa được bảo vệ an toàn đòi hỏi **owner rõ ràng, custodian có trách nhiệm, lưu trữ đúng ranh giới, phân quyền thao tác tối thiểu và có bằng chứng kiểm toán**.

Trong hệ thống Java dùng **KMS/HSM, DEK/KEK, chữ ký số, HMAC, key agreement và envelope encryption**, custodian không nhất thiết được đọc raw key. Họ phải bảo đảm **chuỗi custody, IAM grants, dual control khi cần, recovery, rotation, thu hồi, hủy và audit** được duy trì qua thay đổi nhân sự, ứng dụng và phiên bản khóa.

**Giữ khóa an toàn không chỉ là không làm lộ byte của khóa; đó còn là biết ai chịu trách nhiệm, ai có thể sử dụng quyền mật mã, ai được phép thay đổi kiểm soát và làm thế nào chứng minh mọi bước trong vòng đời đã được thực hiện đúng.**
