# Drift detection

**Drift detection** là quá trình so sánh trạng thái thực tế của hệ thống quản lý khóa với trạng thái mong muốn đã được phê duyệt, sau đó phát hiện và đánh giá mọi sai lệch. Trạng thái mong muốn có thể quy định khóa phải nằm trong HSM, không được export, chỉ cho phép một số workload sử dụng, phải rotate theo cryptoperiod, có backup được bảo vệ và phải phát audit event. Trạng thái thực tế được thu thập từ KMS, HSM, Java KeyStore, IAM, certificate platform, backup service và workload.

Drift có thể xuất hiện do thay đổi thủ công, cấu hình IaC không được áp dụng, quyền bị mở rộng, key version không được rotate, certificate sắp hết hạn, logging bị tắt hoặc backup được tạo ngoài quy trình. Không phải mọi sai lệch đều là tấn công, nhưng mọi sai lệch quan trọng cần có owner, lý do, thời hạn và bằng chứng phê duyệt. Drift detection giúp phát hiện cấu hình đang rời khỏi policy trước khi sai lệch trở thành sự cố.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Automation và vận hành**. Nội dung kết nối drift detection với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, restore, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Desired state và observed state

Drift detection cần hai nguồn thông tin:

- **Desired state:** trạng thái được tổ chức phê duyệt, thường được mô tả trong policy, inventory, cấu hình IaC/GitOps, key standard hoặc change record.
- **Observed state:** trạng thái được hệ thống thực thi báo cáo tại thời điểm thu thập, ví dụ key attributes, IAM grants, provider configuration, certificate status và backup policy.

Ví dụ desired state yêu cầu private signing key phải non-exportable, nằm trong HSM production, chỉ cho phép workload ký và phải ghi audit cho mỗi operation. Nếu observed state cho thấy key có thuộc tính extractable hoặc role runtime có quyền export, hệ thống phát hiện drift.

~~~mermaid
flowchart TD
    A["Desired state<br/>Policy / IaC / inventory"] --> C["Normalize + compare"]
    B["Observed state<br/>KMS / HSM / IAM / PKI / backup"] --> C
    C --> D{"Có sai lệch?"}
    D -- "Không" --> E["Record compliant snapshot"]
    D -- "Có" --> F["Classify drift + risk"]
    F --> G["Alert / ticket / approval"]
    G --> H["Remediate hoặc accept exception"]
    H --> I["Verify observed state"]
    I --> J["Audit + update baseline"]
~~~

Desired state phải có owner và nguồn tin cậy. Nếu cả baseline lẫn hệ thống thực tế đều bị sửa bởi cùng một principal, phép so sánh có thể không phát hiện thay đổi trái phép.

## 2. Drift khác với event và vulnerability như thế nào?

Các khái niệm liên quan nhưng không giống nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Event monitoring | Điều gì vừa xảy ra? | Một role vừa được cấp quyền decrypt. |
| Drift detection | Trạng thái hiện tại có lệch policy không? | Role hiện có quyền decrypt dù desired state không cho phép. |
| Vulnerability scanning | Có điểm yếu đã biết nào tồn tại không? | Provider/JDK có phiên bản chứa lỗ hổng. |
| Compliance check | Trạng thái có đáp ứng một yêu cầu kiểm soát không? | Key không được export và có audit đầy đủ. |
| Configuration reconciliation | Cần đưa trạng thái về desired state bằng cách nào? | Thu hồi grant ngoài policy sau approval. |

Event có thể xảy ra nhưng không tạo drift, ví dụ rotation hợp lệ tạo key version mới theo kế hoạch. Drift có thể tồn tại lâu mà không có event mới, ví dụ một quyền export đã được cấp từ tháng trước. Vì vậy, cần kết hợp event-driven monitoring với kiểm tra trạng thái định kỳ.

## 3. Xác định phạm vi cần theo dõi

Drift detection nên bao phủ các tài sản và cấu hình có ảnh hưởng đến tính bí mật, toàn vẹn, khả dụng và khả năng khôi phục của khóa:

- KMS key, key version, alias, tags và key policy.
- HSM partition, token, object attributes, role và security domain.
- Java KeyStore, PKCS#12/JKS, PKCS#11 provider và trust store.
- IAM role, service account, workload identity và permission grant.
- Thuật toán, key size, curve, purpose và exportability.
- Rotation schedule, cryptoperiod, disable/revoke và destruction schedule.
- Backup, wrapped DEK, KEK reference, replication và restore policy.
- Certificate, CA, trust anchor, validity, SAN và revocation state.
- Audit logging, SIEM destination, retention và alert configuration.
- Secret manager reference và credential dùng để gọi KMS/HSM.

Phạm vi nên được liên kết với inventory có owner, environment, tenant, application consumer và mức độ quan trọng. Không thể phát hiện một key bị thiếu khỏi HSM nếu inventory không biết key đó phải tồn tại.

## 4. Xây dựng nguồn desired state đáng tin cậy

Desired state thường được hình thành từ nhiều nguồn:

1. Security standard quy định thuật toán, key size, purpose và protection level.
2. Key inventory mô tả từng key ID, owner, consumer, cryptoperiod và trạng thái mong muốn.
3. IaC/GitOps mô tả KMS resource, policy, IAM, logging và backup configuration.
4. Change/approval record cho phép ngoại lệ có thời hạn.
5. Certificate policy và rotation schedule mô tả yêu cầu PKI.
6. Recovery plan mô tả backup, replication và key version cần giữ.

Không nên để nhiều nguồn cùng được xem là source of truth mà không quy định thứ tự ưu tiên. Ví dụ, nếu file IaC yêu cầu non-exportable nhưng inventory ghi exportable, hệ thống cần báo conflict thay vì tự chọn một giá trị.

Mỗi desired-state record nên có version, owner, thời điểm hiệu lực, nguồn phê duyệt và checksum/signature nếu cần chống sửa đổi. Chỉ người có quyền mới được cập nhật baseline.

## 5. Nội dung một key baseline

Một baseline có thể mô tả các thuộc tính sau:

| Thuộc tính | Ví dụ desired state |
|---|---|
| Key ID | payments-signing-key |
| Key type | Private signing key |
| Algorithm/profile | RSA-PSS hoặc ECDSA theo profile được duyệt |
| Key size/curve | Theo security standard |
| Backend | HSM production partition |
| Exportability | Non-exportable |
| Purpose | Document signing |
| Allowed principals | Signing workload và operator được phê duyệt |
| Allowed operations | Sign; verify nếu backend hỗ trợ |
| Rotation | Theo cryptoperiod và policy |
| Backup | HSM backup domain được phê duyệt |
| Audit | Sign, policy change, export, backup và destruction |
| State | Enabled; version cũ chỉ decrypt/verify nếu cần |

Baseline cần tránh đưa key bytes, password, PIN hoặc token vào file cấu hình. Nó mô tả metadata và policy, không lưu vật liệu bí mật.

## 6. Các nhóm drift thường gặp

| Nhóm | Ví dụ sai lệch |
|---|---|
| Identity/access drift | Principal mới có quyền decrypt hoặc export |
| Key attribute drift | Key chuyển từ non-exportable sang extractable |
| Algorithm drift | Key mới dùng thuật toán hoặc key size ngoài standard |
| Lifecycle drift | Rotation quá hạn, key hết cryptoperiod vẫn active |
| Backend drift | Private key rời HSM sang software keystore |
| Policy drift | Key policy bị mở rộng hoặc mất điều kiện encryption context |
| Backup/recovery drift | Backup không còn immutable hoặc KEK version bị xóa sớm |
| Certificate drift | Certificate sắp hết hạn, trust anchor thay đổi ngoài kế hoạch |
| Audit drift | Logging bị disable, retention bị rút ngắn hoặc destination bị đổi |
| Inventory drift | Key không có owner, key version không được đăng ký hoặc resource biến mất |

Một thay đổi có thể thuộc nhiều nhóm. Ví dụ, chuyển key từ HSM sang file PKCS#12 vừa là backend drift, exportability drift và có thể là policy drift.

## 7. Thu thập observed state

Observed state có thể được thu thập qua:

- KMS inventory/API và resource configuration.
- HSM management interface, PKCS#11 attributes và device audit.
- Cloud IAM policy và identity provider.
- Secret manager metadata và access policy.
- Certificate inventory, CA/OCSP/CRL và trust store.
- Backup catalog, object storage policy và restore test.
- Application/provider configuration và deployment manifest.
- Audit event, SIEM và change-management system.

Ưu tiên API/read-only role được nhà cung cấp hỗ trợ. Không thu thập bằng cách export key material để “kiểm tra” trạng thái. Nếu backend không cung cấp một thuộc tính, ghi nhận là unknown hoặc not observable; không suy luận giá trị từ việc operation trước đó thành công.

Collector cần xác thực nguồn, phân biệt event time với collection time, ghi phiên bản schema và kiểm tra độ mới của snapshot. Snapshot cũ không thể được coi là observed state hiện tại.

## 8. Chuẩn hóa trước khi so sánh

Hai hệ thống có thể biểu diễn cùng một policy theo thứ tự hoặc định dạng khác nhau. Trước khi so sánh, cần chuẩn hóa:

- Tên thuật toán theo canonical name và profile.
- Principal ID theo định danh ổn định, không chỉ display name.
- Key ID/version và backend resource ID.
- Thời gian về UTC và cùng quy tắc timezone.
- Danh sách permission theo tập operation chuẩn.
- Policy condition theo cấu trúc có thể so sánh.
- Metadata bỏ qua field biến động không ảnh hưởng security, như last-seen timestamp.

Không xóa các field quan trọng chỉ để giảm noise. Ví dụ, bỏ qua destination, key version hoặc exportability sẽ khiến drift nghiêm trọng không được phát hiện.

Với policy JSON, có thể canonicalize object key ordering và normalize list theo semantics của policy. Không sort list nếu thứ tự có ý nghĩa đối với rule evaluation.

## 9. So sánh cấu hình và phát hiện drift

Quy trình cơ bản:

1. Đọc desired state đã được phê duyệt.
2. Thu thập observed state từ backend.
3. Kiểm tra nguồn, timestamp, schema và completeness.
4. Chuẩn hóa hai biểu diễn.
5. So sánh theo field và security invariant.
6. Phân loại drift, mức độ nghiêm trọng và owner.
7. Tạo finding, alert hoặc ticket.
8. Sau remediation, thu thập lại và xác minh.

Không nên chỉ hash toàn bộ object rồi báo “khác”. Hash giúp phát hiện thay đổi nhanh nhưng không giải thích field nào thay đổi, có hợp lệ hay không và rủi ro ra sao. Finding cần giữ diff có chọn lọc và reference tới snapshot được bảo vệ.

## 10. Ví dụ desired state và observed state

Desired state:

~~~yaml
keyId: production/customer-data-kek
backend: approved-kms
purpose: envelope-encryption
exportability: non-exportable
allowedOperations:
  - encrypt
  - decrypt
allowedPrincipals:
  - workload:customer-api
rotation:
  maxAgeDays: 365
audit:
  required: true
  events:
    - encrypt
    - decrypt
    - policy-change
    - disable
    - destroy
~~~

Observed state được backend trả về:

~~~yaml
keyId: production/customer-data-kek
backend: approved-kms
purpose: envelope-encryption
exportability: exportable
allowedOperations:
  - encrypt
  - decrypt
  - export
allowedPrincipals:
  - workload:customer-api
  - user:temporary-admin
rotation:
  lastRotatedAt: 2025-09-01T00:00:00Z
audit:
  required: true
  events:
    - encrypt
    - decrypt
    - policy-change
~~~

Các drift cần phát hiện: key có thể export, operation export được bật, principal tạm thời có quyền, rotation có thể quá hạn và event disable/destroy không nằm trong tập audit mong muốn. Finding phải kiểm tra thời điểm hiện tại, exception đang có hiệu lực và policy cụ thể trước khi kết luận mức độ.

## 11. Drift về quyền truy cập

Permission drift thường nguy hiểm vì quyền có thể được mở rộng mà không thay đổi key material.

Theo dõi:

- Principal mới được grant encrypt/decrypt/sign/export.
- Role runtime nhận quyền admin hoặc wildcard.
- Condition về tenant, environment, encryption context bị bỏ.
- User/service account không còn owner nhưng vẫn có quyền.
- Quyền tạm thời không hết hạn.
- Trust relationship cho workload identity thay đổi.
- Policy bị thay bởi một bản rộng hơn hoặc mất deny rule.

Một số quyền có thể được cấp tạm thời trong migration hoặc incident. Exception phải có owner, approval, scope và expiry. Khi hết hạn, drift detection cần xác nhận quyền đã được thu hồi thật sự.

## 12. Drift về key attributes và exportability

Key attributes quyết định cách khóa được sử dụng và bảo vệ. Các field quan trọng gồm:

- Extractable/exportable hoặc non-exportable.
- Sensitive attribute.
- Allowed mechanisms/operations.
- Key usage và purpose.
- Key size, curve và algorithm.
- Modifiable, copyable hoặc destroyable nếu backend hỗ trợ.
- HSM partition/security domain.

Với PKCS#11, thuộc tính như CKA_SENSITIVE, CKA_EXTRACTABLE và CKA_ALLOWED_MECHANISMS có thể dùng để kiểm tra trạng thái object. Tên, semantics và khả năng thay đổi phụ thuộc token/provider; collector phải dùng API được tài liệu hóa và không giả định mọi thiết bị giống nhau.

Nếu key được yêu cầu non-exportable nhưng observed state không đọc được thuộc tính, kết quả phải là unknown/unverified, không phải compliant.

## 13. Drift về thuật toán và tham số

Một key mới có thể vẫn hoạt động nhưng không còn đáp ứng security standard. Cần theo dõi:

- Thuật toán digest, signature, cipher và MAC.
- Key size hoặc elliptic curve.
- Cipher transformation, mode và padding.
- OAEP/PSS parameters.
- GCM nonce/tag policy.
- KDF và tham số dẫn xuất.
- Provider/backend và module version.

Ví dụ, policy yêu cầu AES-GCM nhưng ứng dụng chuyển sang AES-CBC; key size giảm; RSA-PSS bị thay bằng PKCS#1 v1.5; hoặc provider runtime không còn nằm trong danh sách phê duyệt. Không kết luận chỉ từ tên thuật toán ngắn; cần so sánh transformation/profile và tham số thực tế.

## 14. Drift về rotation và cryptoperiod

Rotation drift xuất hiện khi key không được rotate theo policy hoặc consumer chưa chuyển sang version mới.

Theo dõi:

- Thời điểm tạo và lần rotate gần nhất.
- Cryptoperiod tối đa theo key purpose.
- Rotation schedule và job execution.
- Version mới đã active chưa.
- Consumer còn dùng version cũ không.
- Dữ liệu/backup có còn phụ thuộc version cũ không.
- Key cũ đã chuyển sang decrypt-only, disabled hay vẫn sign/encrypt.

Không tự động xóa key version cũ chỉ vì đã quá tuổi. Một số dữ liệu lịch sử hoặc backup còn cần key đó để giải mã. Drift detection nên phân biệt “quá hạn rotate” với “đủ điều kiện destroy”; hai quyết định này có dependency và approval khác nhau.

## 15. Drift về backup và recovery

Một hệ thống có thể đáp ứng policy khi đang hoạt động nhưng không thể khôi phục sau sự cố nếu backup drift:

- Backup job bị disable hoặc bỏ lỡ lịch.
- Backup không còn immutable hoặc bị đổi retention.
- Wrapped DEK dùng KEK version không còn được giữ.
- HSM backup package không còn restore được.
- Recovery quorum hoặc custodians thay đổi ngoài kế hoạch.
- Backup destination chuyển sang account/region chưa được phê duyệt.
- Restore test quá hạn hoặc thất bại.

Theo dõi cả cấu hình và kết quả thực tế. Một setting “backup enabled” không chứng minh bản backup hợp lệ hoặc có thể restore. Cần kiểm thử restore định kỳ trong môi trường được kiểm soát.

## 16. Drift về certificate và trust

Certificate drift có thể làm gián đoạn dịch vụ hoặc khiến trust bị thay đổi:

- Certificate sắp hết hạn hoặc đã hết hạn.
- Certificate được cấp với SAN/key usage không đúng.
- Certificate issuer hoặc trust anchor thay đổi ngoài kế hoạch.
- Certificate bị revoke nhưng consumer vẫn tin.
- Private key/certificate không còn khớp.
- TLS endpoint dùng certificate hoặc algorithm profile khác baseline.
- CRL/OCSP hoặc trust store không được cập nhật.

Certificate công khai không phải secret, nhưng trạng thái trust và private key liên quan vẫn cần kiểm soát. Drift detection nên liên kết certificate serial/fingerprint với key ID, owner và service consumer.

## 17. Drift về audit và monitoring

Audit configuration cũng là một phần của security posture:

- KMS/HSM audit bị disable.
- Event category nhạy cảm bị bỏ khỏi logging.
- Log destination đổi sang account hoặc endpoint lạ.
- Retention bị rút ngắn.
- Collector mất quyền đọc event.
- SIEM rule hoặc alert bị tắt.
- Clock synchronization bị sai.

Đây là drift có thể làm giảm khả năng phát hiện các drift khác. Vì vậy, thay đổi audit policy cần được giám sát từ một miền độc lập; hệ thống audit không nên chỉ tự ghi vào nơi mà cùng administrator có thể xóa.

## 18. Continuous và scheduled drift detection

Hai mô hình bổ sung cho nhau:

| Mô hình | Cách hoạt động | Phù hợp |
|---|---|---|
| Event-driven | Đánh giá ngay khi nhận event policy/key/IAM change | Phát hiện nhanh thay đổi nhạy cảm |
| Scheduled scan | Định kỳ lấy snapshot và so sánh toàn inventory | Phát hiện drift tồn tại lâu hoặc event bị mất |
| On-demand | Chạy khi audit, migration, release hoặc incident | Xác minh trạng thái tại một thời điểm |
| Continuous reconciliation | Liên tục so sánh và có thể sửa theo policy | Chỉ phù hợp với thuộc tính an toàn, hành động đã được kiểm soát |

Không nên chỉ dựa vào event-driven vì event có thể bị mất hoặc backend không phát đủ chi tiết. Scheduled scan giúp phát hiện trạng thái cuối cùng, nhưng có thể có độ trễ. Tần suất cần dựa trên criticality, khả năng API và chi phí vận hành.

## 19. Phân loại mức độ rủi ro

Không phải mọi drift đều cần phản ứng như nhau. Có thể phân loại:

| Mức | Ví dụ | Hướng xử lý |
|---|---|---|
| Critical | Plaintext exportability bật cho private key production; audit bị tắt trong khi key vẫn được dùng | Alert ngay, containment và phê duyệt xử lý khẩn cấp |
| High | Principal lạ có decrypt/sign; key quá cryptoperiod; KEK backup sắp bị xóa | Điều tra ưu tiên, ticket có SLA ngắn |
| Medium | Rotation job trễ nhưng key chưa quá giới hạn; certificate sắp hết hạn | Owner khắc phục theo deadline |
| Low | Metadata/tag hoặc mô tả lệch baseline nhưng không ảnh hưởng security | Cập nhật có kiểm soát |

Risk score có thể kết hợp key criticality, mức sai lệch, khả năng khai thác, exposure, thời gian tồn tại và độ tin cậy của dữ liệu quan sát. Không nên dùng một điểm số tự động làm quyết định destroy/revoke mà không có quy trình.

## 20. Exception và maintenance window

Một số sai lệch được chấp thuận tạm thời, ví dụ:

- Migration cần key tồn tại ở hai backend trong thời gian ngắn.
- Rotation bị trì hoãn vì consumer chưa tương thích.
- HSM thay thế đang trong giai đoạn đồng bộ.
- Certificate được gia hạn theo quy trình emergency.
- Restore test tạm thời dùng environment riêng.

Exception phải có:

- Finding hoặc control ID liên quan.
- Lý do và risk acceptance.
- Owner chịu trách nhiệm.
- Scope cụ thể: key, principal, environment, operation.
- Thời điểm bắt đầu và hết hạn.
- Biện pháp bù trừ.
- Người phê duyệt và bằng chứng.

Không tạo exception vô thời hạn hoặc wildcard như "ignore all key drift". Khi exception hết hạn, hệ thống phải tự động mở lại finding nếu observed state vẫn lệch.

## 21. False positive và dữ liệu không đầy đủ

Drift detection có thể tạo false positive do:

- Backend cập nhật eventual consistency.
- Alias hoặc metadata thay đổi nhưng key ID không đổi.
- Field do provider sinh tự động.
- Snapshot thu thập ở thời điểm rotation đang diễn ra.
- API trả dữ liệu bị giới hạn bởi quyền collector.
- Policy được biểu diễn khác nhau nhưng có cùng semantics.
- Event bị trễ hoặc đến không đúng thứ tự.

Trước khi mở incident, kiểm tra freshness, completeness, source integrity và change window. Phân biệt rõ:

- compliant: đã quan sát và khớp desired state.
- drifted: đã quan sát và có sai lệch.
- unknown: không thu thập hoặc không xác minh được.
- exception: sai lệch được chấp nhận có thời hạn.
- pending: đang trong workflow thay đổi đã phê duyệt.

Không chuyển unknown thành compliant. Thiếu telemetry là một finding riêng nếu policy yêu cầu phải quan sát được.

## 22. Quy trình xử lý finding

Khi phát hiện drift:

1. Xác minh nguồn observed state và thời điểm thu thập.
2. Xác định key ID/version, principal, backend và thuộc tính lệch.
3. So sánh với desired state và exception còn hiệu lực.
4. Đánh giá impact lên confidentiality, integrity, availability và recoverability.
5. Tìm event, change ticket, deployment và policy update liên quan.
6. Gán owner và mức độ ưu tiên.
7. Chọn alert-only, manual remediation hoặc automated remediation.
8. Thực hiện theo approval và rollback plan.
9. Thu thập observed state mới để xác minh.
10. Đóng finding hoặc tạo exception có thời hạn và audit evidence.

Không đóng finding chỉ vì một lệnh sửa đã chạy. Phải xác minh trạng thái backend sau remediation và đánh giá liệu consumer hoặc dữ liệu có bị ảnh hưởng không.

## 23. Tự động khắc phục: khi nào nên và không nên?

Tự động hóa có thể giảm thời gian tồn tại của drift, nhưng thao tác trên key có thể gây mất dữ liệu hoặc gián đoạn dịch vụ.

Thường phù hợp để tự động:

- Tạo alert/ticket và gán owner.
- Gắn tag hoặc metadata không nhạy cảm theo policy.
- Thu thập snapshot và tạo report.
- Thu hồi một grant tạm thời đã hết hạn nếu workflow đã được phê duyệt.
- Khởi chạy rotation job đã định nghĩa trước, có kiểm tra consumer và rollback.

Thường cần phê duyệt người vận hành:

- Disable hoặc revoke key production.
- Xóa/destroy key hoặc version.
- Thay đổi trust anchor/CA.
- Export/import key hoặc thay đổi exportability.
- Re-encrypt dữ liệu lớn hoặc rewrap toàn bộ DEK.
- Thay đổi policy có thể ảnh hưởng nhiều workload.

Không tự động destroy key chỉ vì inventory không thấy consumer. Consumer có thể đang offline, backup có thể còn phụ thuộc hoặc dữ liệu lịch sử chưa được migrate.

## 24. Reconciliation và fail-safe

Reconciliation đưa observed state về desired state. Cần xác định hành động theo từng field:

- **Alert-only:** chỉ tạo finding; không thay đổi hệ thống.
- **Manual approval:** đề xuất patch, người có quyền xem diff và phê duyệt.
- **Guarded auto-remediation:** tự sửa khi điều kiện rõ ràng, blast radius nhỏ và có rollback.
- **Fail-closed:** chặn operation khi không đáp ứng security invariant quan trọng.

Ví dụ, nếu audit logging bị tắt, hệ thống có thể cảnh báo và chặn export key nhạy cảm. Nếu một tag owner bị thiếu, có thể tạo ticket thay vì disable key.

Reconciliation cần idempotent: chạy lại không tạo thêm thay đổi hoặc gây side effect. Phải kiểm tra trạng thái trước khi hành động và ghi audit cho cả quyết định lẫn kết quả.

## 25. Tích hợp IaC và GitOps

IaC/GitOps giúp lưu desired state trong version control, review thay đổi và tái tạo môi trường. Để phát hiện drift:

- Mỗi KMS key, policy, IAM role và logging destination cần có định nghĩa quản lý.
- Review diff trước khi merge.
- Chạy plan/drift check định kỳ so với resource thực.
- Gắn owner, environment, purpose và key ID vào metadata.
- Phân biệt thay đổi do pipeline với thay đổi thủ công.
- Không lưu secret value hoặc private key trong repository/state plaintext.
- Bảo vệ state file, plan artifact và CI credential.
- Có quy trình import resource đã tồn tại vào IaC mà không tạo key mới ngoài ý muốn.

Không chạy apply tự động cho mọi drift. Một thay đổi thủ công có thể là emergency fix đã được phê duyệt; cần xác minh change record trước khi IaC ghi đè.

## 26. Ví dụ policy-as-code

Ví dụ pseudocode mô tả một số invariant:

~~~text
POLICY production_signing_key:
  REQUIRE backend == "approved-hsm"
  REQUIRE exportability == "non-exportable"
  REQUIRE purpose == "document-signing"
  ALLOW operation IN ["sign"]
  DENY operation IN ["export", "decrypt"]
  REQUIRE audit.events CONTAINS ["sign", "policy-change", "destroy"]
  REQUIRE owner IS NOT EMPTY
  REQUIRE exception.expiresAt > now IF exception.exists
~~~

Đây là policy minh họa, không phải cú pháp của một công cụ cụ thể. Policy thực tế phải phù hợp semantics của KMS/HSM, đặc biệt với key có thể cần verify hoặc unwrap trong một workflow riêng.

Một invariant nên có test positive và negative để chứng minh policy không vô tình chặn operation hợp lệ hoặc cho phép operation ngoài ý muốn.

## 27. Java KeyStore và provider drift

Ứng dụng Java có thể drift khi:

- KeyStore type thay đổi từ PKCS12 sang JKS hoặc provider-specific store.
- Provider order hoặc provider version thay đổi.
- Transformation hoặc signature algorithm đổi ngoài profile.
- Private key chuyển từ HSM handle sang file key có thể export.
- Trust store thêm/xóa certificate hoặc trust anchor.
- File keystore được thay thế ngoài deployment pipeline.
- Security properties hoặc disabled algorithm constraints bị sửa.

Có thể kiểm tra metadata cấu hình và fingerprint của file keystore, nhưng không nên đọc/export private key bytes để so sánh. Dùng key alias, certificate fingerprint, provider name, key algorithm, key size và trạng thái exportability nếu API/backend cung cấp.

Ví dụ kiểm tra type/provider và certificate fingerprint:

~~~java
import java.security.KeyStore;
import java.security.Provider;
import java.security.cert.Certificate;
import java.security.MessageDigest;
import java.util.HexFormat;

KeyStore store = KeyStore.getInstance("PKCS12");
// store đã được load từ nguồn cấu hình được phê duyệt.
Provider provider = store.getProvider();
Certificate certificate = store.getCertificate("service-signing");

if (certificate == null) {
    throw new IllegalStateException("Expected certificate is missing");
}

System.out.println("Observed keystore provider: " + provider.getName());
byte[] fingerprint = MessageDigest.getInstance("SHA-256")
        .digest(certificate.getEncoded());
String certificateFingerprint = HexFormat.of().formatHex(fingerprint);
~~~

Đây là ví dụ minh họa phần metadata public. Store cần được load trước đó; provider thực tế phải là provider được phê duyệt cho môi trường. HexFormat yêu cầu Java 17 trở lên. Không lấy private key hoặc gọi getEncoded() trên private key để tạo fingerprint.

## 28. Drift trong KMS/HSM

KMS/HSM cung cấp API và thuộc tính khác nhau. Một collector nên:

- Dùng read-only role khi có thể.
- Lấy key ID/version, state, algorithm, purpose và policy.
- Lấy exportability/sensitive attributes nếu backend cung cấp.
- Kiểm tra role, partition, replication và backup domain.
- Lấy audit configuration và trạng thái event delivery.
- Kiểm tra key rotation và deletion schedule.
- Phân biệt field không hỗ trợ với field bị thiếu do collector thiếu quyền.

Không gọi operation có side effect chỉ để kiểm tra drift. Ví dụ, không thực hiện export thử trên key production để chứng minh exportability. Dùng metadata/attribute API hoặc key thử trong môi trường kiểm soát.

## 29. Metrics và báo cáo vận hành

Các chỉ số có thể giúp đánh giá hiệu quả:

| Metric | Ý nghĩa |
|---|---|
| Drift count by severity | Số sai lệch theo mức rủi ro |
| Mean time to detect (MTTD) | Thời gian từ lúc drift xuất hiện đến khi phát hiện |
| Mean time to remediate (MTTR) | Thời gian từ finding đến khi xác minh khắc phục |
| Unknown coverage | Tỷ lệ tài sản không thu thập/không xác minh được |
| Exception age | Tuổi và số exception sắp/quá hạn |
| Rotation compliance | Tỷ lệ key được rotate đúng hạn |
| Policy violation rate | Tần suất vi phạm invariant |
| Backup restore success | Tỷ lệ restore test thành công |
| Audit pipeline health | Độ trễ, dropped event và nguồn mất kết nối |

Không tối ưu chỉ số bằng cách đóng finding nhanh hoặc bỏ qua unknown. Báo cáo cần phân biệt drift đã xác minh, exception, false positive và thiếu telemetry.

## 30. Ví dụ thực tế: phát hiện key policy bị mở rộng

Một workload billing-api chỉ được decrypt DEK bằng KEK billing-data-kek trong KMS production. Desired state giới hạn quyền cho workload identity cụ thể và cấm export.

Trong một lần thay đổi thủ công, administrator thêm role temporary-operator với quyền decrypt và export. Event-driven monitor nhận policy update; scheduled scan sau đó xác nhận observed policy khác baseline.

Quy trình:

1. Collector xác minh policy version và key ID.
2. Drift engine so sánh principal và operation với desired state.
3. Finding được phân loại high/critical vì export/decrypt đã mở rộng.
4. SIEM liên kết event cấp quyền với mọi lần sử dụng key sau thay đổi.
5. Owner xác minh change ticket và người phê duyệt.
6. Nếu không có approval, revoke grant và đánh giá các operation đã xảy ra.
7. Thu thập lại policy, xác minh quyền đã trở về baseline.
8. Ghi evidence, cập nhật incident và review quyền tương tự trên các key khác.

Nếu grant là ngoại lệ hợp lệ, phải ghi exception với scope, owner và expiry. Khi hết hạn, drift engine kiểm tra quyền đã được thu hồi chưa.

## 31. Kiểm thử drift detection

Kiểm thử bằng key, policy và identity thử trong môi trường riêng:

| Test | Kết quả mong đợi |
|---|---|
| Thêm principal ngoài baseline | Finding access drift |
| Bật exportability cho key thử | Finding attribute drift |
| Đổi algorithm/key size ngoài standard | Finding crypto-profile drift |
| Bỏ lỡ rotation schedule | Finding lifecycle drift |
| Disable audit event | Finding audit drift và alert |
| Thay backup destination | Finding recovery drift |
| Certificate sắp hết hạn | Finding certificate drift theo ngưỡng |
| Thêm exception còn hiệu lực | Finding được đánh dấu exception, không bị xóa |
| Exception hết hạn | Finding được mở lại nếu drift còn tồn tại |
| Collector thiếu quyền | Trạng thái unknown, không báo compliant |
| Remediation thành công | Snapshot mới xác nhận trạng thái đã sửa |
| Remediation thất bại | Finding vẫn mở và ghi rõ lỗi |

Test cần xác minh cả nguồn dữ liệu, normalize, diff, risk classification, alert, ticket và observed state sau remediation.

## 32. Checklist triển khai Drift detection

Trước khi đưa vào production, hãy xác nhận:

- [ ] Có inventory key ID/version, owner, purpose, backend và consumer.
- [ ] Desired state có source of truth, version, owner và approval.
- [ ] Observed state được thu thập từ KMS/HSM, IAM, PKI, backup và workload.
- [ ] Collector dùng quyền tối thiểu và không export key material.
- [ ] Snapshot có timestamp, source, schema version và freshness check.
- [ ] Normalize không làm mất field bảo mật quan trọng.
- [ ] So sánh theo invariant và có diff giải thích được.
- [ ] Phân loại compliant, drifted, unknown, exception và pending.
- [ ] Theo dõi access, exportability, algorithm, rotation, backup, certificate và audit drift.
- [ ] Exception có owner, scope, approval và expiry.
- [ ] Alert/ticket có key ID, principal, field lệch, severity và evidence.
- [ ] Auto-remediation có giới hạn blast radius, approval và rollback.
- [ ] Không tự động destroy/revoke key khi chưa đánh giá dependency.
- [ ] Sau remediation, thu thập lại observed state để xác minh.
- [ ] Có metrics MTTD, MTTR, exception age và unknown coverage.
- [ ] Có test positive/negative và kiểm tra pipeline khi collector lỗi.

## 33. Checklist điều tra một drift finding

Khi nhận finding, hãy xác nhận:

- [ ] Desired state lấy từ nguồn nào và có version/approval hợp lệ không?
- [ ] Observed snapshot mới và đầy đủ đến mức nào?
- [ ] Key ID/version, backend, owner và consumer nào bị ảnh hưởng?
- [ ] Field nào lệch và security invariant nào bị vi phạm?
- [ ] Có change ticket, maintenance window hoặc exception còn hiệu lực không?
- [ ] Principal hoặc policy nào tạo ra sai lệch?
- [ ] Có operation encrypt/decrypt/sign/export bất thường sau thay đổi không?
- [ ] Backup, certificate hoặc dữ liệu lịch sử có dependency không?
- [ ] Cần alert-only, manual remediation, guarded auto-remediation hay fail-closed?
- [ ] Đã xác minh trạng thái sau khắc phục và bảo toàn audit evidence chưa?

Drift detection giữ trạng thái quản lý khóa gần với policy đã phê duyệt bằng cách liên tục so sánh desired state và observed state. Hiệu quả phụ thuộc vào inventory đầy đủ, baseline đáng tin cậy, dữ liệu quan sát mới, phép so sánh có ngữ nghĩa và quy trình xử lý có owner. Tự động hóa nên bắt đầu từ phát hiện, phân loại và tạo bằng chứng; mọi thay đổi có thể làm mất khả năng giải mã, ký hoặc khôi phục phải đi qua kiểm soát phù hợp và được xác minh sau khi thực hiện.
