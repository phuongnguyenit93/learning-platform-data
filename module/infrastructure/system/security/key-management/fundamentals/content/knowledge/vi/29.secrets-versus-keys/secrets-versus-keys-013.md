# Secret access audit

**Secret access audit** là hoạt động ghi nhận, bảo vệ, phân tích và rà soát các sự kiện liên quan đến việc truy cập bí mật trong hệ thống. Mỗi sự kiện cần cho biết danh tính nào đã yêu cầu thao tác gì trên secret nào, vào thời điểm nào, từ workload hoặc nguồn nào, kết quả ra sao và quyết định phân quyền dựa trên policy nào. Mục tiêu là giúp tổ chức phát hiện truy cập trái phép, điều tra sự cố, chứng minh việc tuân thủ và xác nhận quyền truy cập vẫn phù hợp với công việc.

Secret có thể là database password, API token, client secret, SSH private key, TLS private key, signing key, encryption key, password pepper hoặc credential dùng để gọi KMS/HSM. Vì vậy, audit cần phối hợp giữa secret manager, IAM, KMS/HSM, nền tảng workload, hệ thống logging và SIEM. Một log chỉ ghi “đã đọc secret” mà không xác định được principal, resource, operation và kết quả sẽ không đủ để điều tra.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Secrets và key**. Nội dung kết nối kiểm toán truy cập secret với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Vì sao phải audit truy cập secret?

Secret thường cấp quyền trực tiếp đến dữ liệu hoặc hành động quan trọng. Một service password có thể mở database; một API token có thể tạo tài nguyên cloud; một private key có thể ký giao dịch hoặc xác thực máy chủ. Nếu secret bị đọc bởi principal không được phép, hậu quả có thể lan rộng hơn phạm vi hệ thống lưu secret.

Audit giúp trả lời các câu hỏi vận hành và điều tra:

- Ai hoặc workload nào đã yêu cầu đọc secret?
- Secret hoặc phiên bản nào đã được truy cập?
- Yêu cầu được cho phép hay bị từ chối?
- Principal đã xác thực bằng identity, role hoặc session nào?
- Yêu cầu đến từ workload, môi trường, địa chỉ hoặc thiết bị nào?
- Có approval, ticket hoặc lý do công việc gắn với thao tác nhạy cảm không?
- Ai đã tạo, thay đổi policy, cấp quyền, rotate, disable hoặc xóa secret?
- Có truy cập bất thường trước, trong hoặc sau một sự cố không?
- Credential bị lộ đã được truy cập hoặc sử dụng ở đâu?

Nếu không có audit trail đáng tin cậy, tổ chức khó phân biệt hoạt động bình thường với hành vi đánh cắp secret, khó giới hạn phạm vi ảnh hưởng và khó chứng minh rằng quyền truy cập được kiểm soát.

## 2. Phân biệt secret access audit với log ứng dụng

Log ứng dụng thường mô tả trạng thái xử lý nghiệp vụ. Secret access audit ghi nhận quyết định và thao tác trên tài nguyên bí mật. Hai loại log bổ sung cho nhau nhưng không thay thế nhau.

| Loại telemetry | Ví dụ | Mục đích |
|---|---|---|
| Secret access audit | Workload orders-api đọc version 7 của secret database credential; quyết định allow | Biết ai đã truy cập secret và kết quả truy cập. |
| IAM audit | Role được gán cho service account; policy được sửa | Biết ai thay đổi danh tính và quyền. |
| KMS/HSM audit | Key orders-data-kek thực hiện decrypt hoặc unwrap | Biết thao tác mật mã nào đã diễn ra trên key. |
| Application log | Kết nối database thất bại với mã lỗi xác thực | Hiểu tác động nghiệp vụ, không ghi credential. |
| Workload/security telemetry | Container mới được tạo, process bất thường, token exchange | Cung cấp ngữ cảnh về workload thực hiện truy cập. |

Một secret manager có thể ghi nhận ứng dụng đã lấy password, nhưng không nhất thiết biết password đó được dùng để đăng nhập database thành công. Database audit có thể ghi nhận principal đã kết nối, nhưng không biết secret manager nào đã cấp password. Cần nối các nguồn bằng request ID, workload identity, thời gian, secret reference và key ID phù hợp.

## 3. Phân biệt control plane và data plane

Nền tảng quản lý secret thường có hai nhóm hoạt động:

- **Control plane:** tạo secret, thay đổi metadata, cập nhật policy, cấp/revoke quyền, rotate version, disable hoặc xóa resource.
- **Data plane:** đọc secret value, lấy phiên bản, dùng token, unwrap key hoặc thực hiện operation mật mã.

Cả hai nhóm đều cần audit. Một kẻ tấn công có thể không đọc secret ngay; họ có thể sửa policy để cấp quyền cho mình rồi đọc sau. Nếu chỉ audit thao tác read, tổ chức có thể bỏ sót bước chuẩn bị quan trọng.

~~~mermaid
flowchart TD
    A["Principal / workload"] --> B["IAM authentication"]
    B --> C["Secret manager policy"]
    C --> D{"Decision"}
    D -- "Allow" --> E["Secret data plane: read/version"]
    D -- "Deny" --> F["Denied access event"]
    E --> G["Secret access audit"]
    F --> G
    H["Control plane: policy / grant / rotate / delete"] --> G
    I["KMS / HSM operation audit"] --> J["Central audit pipeline"]
    G --> J
    J --> K["SIEM / detection / investigation"]
~~~

Audit control plane cho biết cấu hình nào đã thay đổi; audit data plane cho biết bí mật đã được yêu cầu sử dụng. Khi điều tra, cần dựng lại chuỗi sự kiện từ thay đổi quyền đến lần đọc secret và các operation sau đó.

## 4. Xác định phạm vi secret cần audit

Trước khi cấu hình logging, cần có inventory để biết secret nằm ở đâu và hệ thống nào có thể truy cập. Phạm vi thường gồm:

- Secret manager hoặc vault tập trung.
- KMS/HSM và key management service.
- Kubernetes Secrets, CSI secret mounts và workload identity integration.
- Database credential, password vault và credential broker.
- CI/CD secret store, deploy token và signing credential.
- Cloud access key, API token, OAuth client secret và refresh token.
- SSH key, TLS certificate/private key và code-signing key.
- Secret được lưu trong file cấu hình, hệ thống legacy hoặc thiết bị.

Mỗi secret nên có metadata tối thiểu: resource ID ổn định, owner, purpose, environment, tenant/scope, classification, version, nguồn cấp phát, hệ thống tiêu thụ và chính sách retention. Metadata này giúp audit event có thể liên kết với tài sản mà không phải ghi secret value.

Không phải mọi dữ liệu nhạy cảm đều là secret. Certificate công khai hoặc username có thể cần bảo vệ tính toàn vẹn và quyền riêng tư nhưng không có cùng semantics với password hoặc private key. Phân loại đúng giúp đặt mức audit phù hợp.

## 5. Những sự kiện cần ghi nhận

Danh mục event nên bao phủ cả vòng đời và quyền truy cập:

| Nhóm sự kiện | Ví dụ |
|---|---|
| Authentication | Principal đăng nhập vault, token exchange, session mở/đóng |
| Read/access | Đọc secret, lấy version, mount secret, resolve reference |
| Denied access | Bị từ chối do thiếu role, sai tenant hoặc policy |
| Enumeration | Liệt kê secret, tìm kiếm metadata, duyệt path |
| Create/update | Tạo secret, ghi version mới, cập nhật metadata |
| Permission change | Grant/revoke role, sửa policy, thay đổi ACL |
| Rotation | Bắt đầu, hoàn tất hoặc thất bại rotation |
| Disable/revoke | Disable version, revoke credential, thu hồi session |
| Delete/destroy | Xóa secret, schedule destruction, hủy key |
| Export/backup/restore | Export secret, tạo backup, restore version |
| Break-glass | Dùng quyền khẩn cấp hoặc emergency access |
| Administrative | Thay đổi audit configuration, retention hoặc logging destination |

Ghi cả thao tác thành công và thất bại. Một loạt request bị deny có thể là dấu hiệu dò tìm secret hoặc credential bị cấu hình sai. Việc không ghi denied event làm mất một nguồn tín hiệu quan trọng.

## 6. Thiết kế event schema nhất quán

Audit event nên có schema ổn định, dễ tìm kiếm và nối giữa các hệ thống. Một event có thể chứa:

| Field | Ý nghĩa |
|---|---|
| eventId | ID duy nhất của event |
| eventTime | Thời điểm UTC do nguồn ghi nhận |
| eventType | Loại hành động như secret.read hoặc policy.update |
| outcome | success, denied hoặc failure |
| principalId | ID ổn định của user/service account/workload |
| principalType | Human, service, workload, admin hoặc emergency identity |
| authContext | Cơ chế xác thực, role/session và assurance level phù hợp |
| resourceId | ID secret/key; không phải secret value |
| resourceVersion | Version được yêu cầu hoặc thay đổi |
| operation | Read, list, create, rotate, delete, unwrap... |
| source | Workload, cluster, namespace, host hoặc client |
| networkContext | IP/zone/device context nếu cần và được phép lưu |
| policyDecision | Policy/rule/version đã quyết định allow/deny |
| requestId | ID nối với request hoặc trace khác |
| reason | Lý do nghiệp vụ hoặc mã lỗi đã được chuẩn hóa |
| approvalRef | Ticket/approval ID cho thao tác cần phê duyệt |

Không phải event nào cũng có mọi field. Schema nên cho phép field không áp dụng ở dạng null/omitted, nhưng không được thiếu principal, resource, operation, timestamp hoặc outcome đối với sự kiện truy cập nhạy cảm.

## 7. Ví dụ audit event cho lần đọc secret

Ví dụ JSON dưới đây ghi lại metadata của một lần đọc secret. Giá trị password/token không xuất hiện trong event:

~~~json
{
  "eventId": "evt-01J8Q7K6M3",
  "eventTime": "2026-11-28T03:15:22.418Z",
  "eventType": "secret.read",
  "outcome": "success",
  "principal": {
    "id": "spiffe://prod.example/ns/orders/sa/orders-api",
    "type": "workload",
    "role": "orders-db-reader"
  },
  "resource": {
    "id": "secret://production/orders/database-credential",
    "version": "7",
    "classification": "restricted"
  },
  "operation": "read",
  "source": {
    "cluster": "prod-cluster-a",
    "namespace": "orders",
    "workload": "orders-api",
    "instance": "pod-7f6d9"
  },
  "policy": {
    "decision": "allow",
    "policyId": "policy-orders-runtime",
    "policyVersion": "12"
  },
  "requestId": "req-8b2f91",
  "reasonCode": "runtime-secret-injection"
}
~~~

Tên resource, principal và ID trong ví dụ là dữ liệu minh họa. Trong hệ thống thật, dùng identifier ổn định, có thể tra cứu trong inventory và không tiết lộ secret value.

## 8. Ghi nhận denied và failed access

Event bị từ chối có giá trị điều tra tương đương event thành công. Cần phân biệt:

- **Denied:** policy đã đánh giá và từ chối request.
- **Failed:** request không hoàn tất vì lỗi kỹ thuật như timeout, backend unavailable hoặc invalid request.
- **Authentication failure:** principal không xác thực được hoặc credential không hợp lệ.

Ví dụ event denied:

~~~json
{
  "eventType": "secret.read",
  "eventTime": "2026-11-28T03:18:02Z",
  "outcome": "denied",
  "principalId": "spiffe://prod.example/ns/reporting/sa/report-api",
  "resourceId": "secret://production/payments/provider-token",
  "operation": "read",
  "policyDecision": "deny",
  "reasonCode": "missing-role",
  "requestId": "req-1f903a"
}
~~~

Không ghi raw request chứa token hoặc password sai vào audit. Có thể ghi mã lỗi, loại authentication failure và nguồn request đã được làm sạch. Nếu log mọi lần thất bại, cần giới hạn tốc độ và bảo vệ pipeline khỏi bị flood.

## 9. Nhận diện principal: người dùng và workload

Audit chỉ hữu ích khi xác định được ai thực hiện hành động. Tránh chỉ ghi username chung như admin, app hoặc root nếu có thể dùng ID ổn định hơn.

Đối với người dùng:

- User ID ổn định, không chỉ display name.
- Identity provider và tenant/organization.
- Role, group hoặc privilege context tại thời điểm truy cập.
- MFA/assurance context khi chính sách yêu cầu.
- Session ID hoặc authentication event ID.

Đối với workload:

- Workload identity hoặc service account ID.
- Cluster, namespace, service và environment.
- Instance/pod/container identity nếu cần điều tra.
- Identity issuer, token audience và thời hạn token ở mức metadata.
- Deployment/version hoặc release ID để liên kết với thay đổi ứng dụng.

Không dùng IP address làm danh tính chính. IP có thể thay đổi, dùng chung qua NAT hoặc bị proxy che khuất. Nên kết hợp principal ID, workload identity và network context.

## 10. Ghi nhận resource và version

Audit event cần chỉ ra secret nào được truy cập. Tên hiển thị có thể thay đổi; resource ID ổn định giúp truy vấn lịch sử chính xác hơn.

Nên ghi:

- Secret resource ID hoặc key ID.
- Version được đọc, tạo, disable hoặc xóa.
- Environment/tenant scope.
- Owner và purpose nếu metadata có sẵn.
- Loại thao tác và kết quả.

Không ghi secret value, password, private key bytes, DEK dạng rõ hoặc token. Tránh ghi hash không có mục đích của secret value: hash của secret có entropy thấp có thể hỗ trợ đoán offline. Nếu cần fingerprint để so sánh version, dùng cơ chế riêng được đánh giá, giới hạn quyền và không thay thế secret manager version ID.

## 11. Audit việc liệt kê và tìm kiếm secret

Không chỉ thao tác read mới nhạy cảm. Khả năng liệt kê tên hoặc metadata secret có thể tiết lộ kiến trúc, tên hệ thống, tenant, môi trường và loại credential.

Nên audit:

- Liệt kê toàn bộ secret hoặc một path/prefix.
- Tìm kiếm theo tag, owner hoặc environment.
- Liệt kê version và trạng thái.
- Đọc metadata nhạy cảm.
- Export danh sách inventory.
- Truy vấn quyền hoặc policy liên quan secret.

Một workload runtime thường chỉ cần truy cập một số resource cụ thể, không cần quyền enumerate toàn vault. Hành vi list rộng hoặc tăng đột biến có thể là tín hiệu reconnaissance.

## 12. Audit thay đổi policy và quyền

Thay đổi quyền có thể mở đường cho truy cập secret trong tương lai. Event control plane cần ghi:

- Ai tạo, sửa hoặc xóa policy.
- Principal/role nào được cấp hoặc thu hồi quyền.
- Resource/path/tenant scope bị ảnh hưởng.
- Operation được cấp: read, list, write, rotate, export, delete hoặc admin.
- Policy version trước và sau thay đổi.
- Approval/ticket và lý do.
- Kết quả áp dụng và thời điểm có hiệu lực.

Không chỉ lưu policy mới. Cần có khả năng xem lại lịch sử để xác định ai đã mở rộng quyền, quyền nào đã tồn tại tại thời điểm truy cập và có thay đổi nào ngay trước sự cố.

Đối với thao tác nhạy cảm như cấp quyền đọc toàn bộ production secrets, yêu cầu approval hoặc dual control. Người tạo policy không nên mặc nhiên là người duy nhất phê duyệt và tự cấp quyền.

## 13. Audit rotation, revocation và destruction

Rotation và destruction cũng là sự kiện bảo mật cần truy vết. Nên ghi:

| Hoạt động | Trường thông tin cần có |
|---|---|
| Rotation start | Secret/key ID, version cũ, version dự kiến, actor, lý do |
| Rotation success | Version mới, thời điểm active, hệ thống consumer được cập nhật |
| Rotation failure | Bước thất bại, mã lỗi, trạng thái version, retry/reference |
| Revoke/disable | Resource/version, actor, policy/approval, tác động |
| Delete | Resource ID, thời điểm, retention/soft-delete state |
| Destroy | Key ID/version, destruction request, approval, kết quả từ backend |
| Restore | Version được phục hồi, người phê duyệt, nguồn backup, môi trường đích |

Không ghi key material khi rotate hoặc backup. Audit cần cho biết version nào được tạo/thu hồi và trạng thái thay đổi, để điều tra có thể xác định secret cũ còn được dùng ở đâu.

## 14. Liên kết secret manager với KMS/HSM audit

Secret manager thường ghi nhận lần đọc secret; KMS/HSM ghi nhận thao tác trên key. Hai nguồn cung cấp góc nhìn khác nhau:

- Secret manager audit cho biết principal lấy secret hoặc version nào.
- KMS audit cho biết key nào thực hiện encrypt, decrypt, wrap, unwrap, sign hoặc verify.
- HSM audit có thể ghi session, role, token, object handle và operation theo khả năng thiết bị.

Với envelope encryption, ứng dụng có thể lấy ciphertext/wrapped DEK từ secret store rồi yêu cầu KMS unwrap DEK. Cần nối event của secret store với KMS operation bằng request ID, workload identity, key ID, thời gian và trace context.

Không giả định một lần đọc secret luôn tạo đúng một event KMS. Secret manager có thể cache plaintext hoặc DEK; một operation có thể được batch; provider có thể dùng session hoặc data key cache. Tài liệu backend và kiến trúc thực tế quyết định mức độ quan sát được.

## 15. Không ghi secret value vào audit log

Audit phải ghi lại **sự kiện truy cập**, không sao chép bí mật được truy cập. Nếu log chứa secret value, hệ thống logging trở thành một kho secret thứ hai, thường có nhiều người và công cụ được quyền tìm kiếm hơn vault ban đầu.

Không ghi:

- Password, passphrase, API token hoặc Authorization header.
- Private key, secret key, DEK hoặc plaintext sau giải mã.
- Request/response body chứa credential.
- PIN, recovery code, refresh token hoặc cookie session.
- Environment dump hoặc toàn bộ config có secret.

Có thể ghi:

- Principal ID và role.
- Secret resource ID và version.
- Operation, timestamp và outcome.
- Policy decision, request ID và approval reference.
- Workload, environment và source context đã được làm sạch.

Redaction phải diễn ra trước khi event rời process hoặc trước khi được gửi vào pipeline log. Chỉ che ở giao diện tìm kiếm là chưa đủ nếu raw event vẫn chứa secret trong storage.

## 16. Bảo vệ audit log khỏi sửa đổi

Audit log có giá trị chứng cứ. Nếu principal có quyền truy cập secret cũng có thể xóa hoặc sửa log, kẻ tấn công có thể che giấu hoạt động.

Các biện pháp:

- Gửi audit event tới hệ thống logging tách biệt với workload nguồn.
- Dùng append-only hoặc immutable/WORM storage theo retention.
- Tách quyền ghi log, đọc log, quản trị log và xóa log.
- Dùng account/project/security domain riêng cho audit storage.
- Mã hóa log khi truyền và khi lưu.
- Đồng bộ thời gian và theo dõi clock drift.
- Bảo vệ cấu hình audit khỏi bị tắt hoặc giảm phạm vi.
- Ghi nhận việc thay đổi logging, retention và destination như một audit event riêng.

Hash chain hoặc chữ ký event có thể tăng khả năng phát hiện sửa đổi, nhưng cần quản lý khóa ký và anchor độc lập. Một hash chain không bảo vệ được log nếu kẻ tấn công kiểm soát cả log store lẫn khóa/điểm neo.

## 17. Phân quyền truy cập audit log

Không phải ai cũng cần xem mọi audit event. Log có thể chứa thông tin về cấu trúc hạ tầng, danh tính, hoạt động của nhân viên và resource nhạy cảm.

Nên tách các quyền:

| Quyền | Người/nhóm thường cần |
|---|---|
| Emit/write | Secret manager, KMS/HSM gateway hoặc collector được xác thực |
| Search/read | Security analyst, incident responder theo phạm vi |
| Configure | Security platform owner hoặc audit administrator |
| Export | Người được phê duyệt cho điều tra/compliance |
| Delete/retention override | Quyền đặc biệt, dual control và audit riêng |

Workload thông thường không được xóa audit event. Quản trị viên vault không nên mặc định có quyền xóa bằng chứng audit. Nếu cần export log cho điều tra, phải bảo vệ bản export và ghi lại ai đã truy cập.

## 18. Tích hợp SIEM và pipeline tập trung

Audit event từ secret manager, IAM, KMS/HSM, cloud control plane và workload nên được chuyển đến pipeline tập trung để chuẩn hóa và phân tích.

Một pipeline điển hình:

~~~mermaid
flowchart LR
    A["Secret manager"] --> E["Collector / event bus"]
    B["IAM / identity provider"] --> E
    C["KMS / HSM"] --> E
    D["Cloud / workload audit"] --> E
    E --> F["Normalize + redact + validate"]
    F --> G["Immutable audit store"]
    F --> H["SIEM / detection rules"]
    H --> I["Alert / case management"]
    G --> J["Investigation / compliance evidence"]
~~~

Pipeline cần xác thực nguồn gửi, kiểm tra schema, chống mất event, xử lý duplicate và bảo đảm thứ tự tương đối khi có thể. Nên lưu source event ID và ingest time để phân biệt thời điểm phát sinh với thời điểm hệ thống nhận event.

Không phụ thuộc vào một dashboard duy nhất. Cần có quy trình kiểm tra pipeline health, event delay, dropped events và thay đổi cấu hình collector.

## 19. Phát hiện truy cập bất thường

Một số tín hiệu có thể dùng để tạo detection:

- Workload đọc secret ngoài danh sách resource bình thường.
- User hoặc service account truy cập secret production từ môi trường development.
- Một principal liệt kê số lượng lớn secret trong thời gian ngắn.
- Nhiều lần denied access tới các path hoặc tenant khác nhau.
- Secret được đọc từ IP, region, cluster hoặc thiết bị mới.
- Truy cập vào giờ hoặc thời điểm không phù hợp với lịch workload.
- Một principal đọc secret ngay sau khi được cấp role mới.
- Thao tác export, backup hoặc restore bất thường.
- Một secret cũ hoặc version đã bị disable tiếp tục được yêu cầu.
- Rotation thất bại nhiều lần hoặc bị dừng trước khi hoàn tất.
- Thay đổi audit policy, log destination hoặc retention ngay trước một lần đọc nhạy cảm.
- Human account đọc hàng loạt secret mà không có ticket hoặc approval.

Không nên tạo cảnh báo chỉ dựa trên một thuộc tính đơn lẻ như IP hoặc giờ truy cập. Cần kết hợp identity, workload, resource, policy change, baseline, request volume và ngữ cảnh thay đổi hợp lệ để giảm false positive.

## 20. Ví dụ detection rule

Ví dụ logic phát hiện một workload đọc nhiều secret ngoài baseline:

~~~text
IF
  principal.type = "workload"
  AND count_distinct(resource.id) > allowed_secret_count
  AND time_window = 10 minutes
  AND NOT approved_rotation_or_restore_window
THEN
  alert = "unusual_secret_enumeration"
  severity = "high"
  include = [principal.id, resources, source, request_ids]
~~~

Đây là pseudocode minh họa, không phải cú pháp SIEM cụ thể. allowed_secret_count phải được xác định theo baseline của workload. Job rotation, backup hoặc deployment có thể truy cập nhiều secret hợp lệ; cần gắn change window hoặc workload identity riêng để phân biệt.

Một rule khác có thể phát hiện quyền vừa được mở rộng rồi secret được đọc:

1. Principal được cấp role mới có quyền đọc secret production.
2. Trong khoảng thời gian ngắn sau đó, principal đọc một hoặc nhiều secret nhạy cảm.
3. Không có approval hoặc change request tương ứng.
4. Tạo alert kết hợp policy event và secret access event.

## 21. Baseline theo workload và người dùng

Baseline mô tả hành vi truy cập thông thường của từng principal:

- Secret/resource nào được đọc.
- Tần suất và khung thời gian.
- Môi trường, cluster, namespace và region.
- Operation được phép.
- Version nào thường được dùng.
- Lịch rotation, deployment và backup.

Baseline không nên trở thành allowlist vĩnh viễn. Khi workload thay đổi, baseline cần được cập nhật qua change process và review. Nếu tự động học mọi hành vi mới mà không có kiểm soát, kẻ tấn công có thể dần làm độc baseline.

Với human access, baseline nên xét role, ticket, on-call schedule, approval và mức độ nhạy cảm của secret. Một quản trị viên có thể cần quyền break-glass nhưng không nên đọc production secrets thường xuyên nếu nhiệm vụ không yêu cầu.

## 22. Break-glass và emergency access

Break-glass là cơ chế cấp quyền khẩn cấp khi quy trình thông thường không đáp ứng được sự cố. Đây là ngoại lệ có rủi ro cao và phải được audit chặt chẽ.

Một quy trình tốt:

1. Người yêu cầu xác thực bằng identity riêng và MFA mạnh.
2. Nêu incident ID, lý do, phạm vi và thời hạn cần quyền.
3. Hệ thống cấp quyền tạm thời với scope tối thiểu.
4. Nếu điều kiện cho phép, yêu cầu dual approval hoặc quorum.
5. Ghi audit cả yêu cầu, phê duyệt, grant, secret read và revoke.
6. Tự động hết hạn quyền sau thời gian ngắn.
7. Rà soát mọi operation thực hiện trong phiên.
8. Rotate secret nếu có khả năng bị lộ trong quá trình khẩn cấp.

Không dùng tài khoản admin dùng chung cho break-glass. Nếu credential khẩn cấp phải được lưu offline, cần quản lý sealed secret, kiểm kê người giữ, kiểm tra định kỳ và ghi nhận mỗi lần mở.

## 23. Rà soát quyền truy cập định kỳ

Audit không chỉ phục vụ điều tra sau sự cố. Dữ liệu truy cập thực tế giúp rà soát xem quyền hiện tại có còn cần thiết không.

Trong access review, cần xem:

- Principal nào đang có quyền đọc secret?
- Principal nào thực sự đã dùng quyền trong kỳ?
- Có role hoặc group nào quá rộng?
- Secret có owner rõ ràng không?
- Workload cũ hoặc service account không còn hoạt động có còn quyền?
- Human access có approval và ticket phù hợp không?
- Quyền export, delete, rotate và administer có bị gộp quá nhiều?
- Có secret/version không còn consumer nhưng vẫn tồn tại?

Không dùng “không có access event” làm bằng chứng duy nhất rằng quyền không cần thiết. Có thể log chưa đầy đủ hoặc workload dùng cache. Cần kết hợp inventory, dependency, owner và kế hoạch thay đổi trước khi revoke.

## 24. Audit truy cập secret trong môi trường nhiều tenant

Trong hệ thống multi-tenant, audit phải giữ được ranh giới tenant:

- Ghi tenant ID hoặc security boundary đã được xác thực.
- Liên kết principal với tenant/workload scope.
- Không cho phép principal tenant A enumerate resource tenant B.
- Ghi lại policy decision và resource scope tại thời điểm truy cập.
- Tách quyền đọc audit theo tenant hoặc chỉ cho phép security role phù hợp xem cross-tenant.
- Không đưa secret value hoặc dữ liệu khách hàng không cần thiết vào event.

Nếu resource path chứa tenant ID, vẫn cần kiểm tra authorization ở backend; không dựa vào việc caller tự truyền path đúng. Cross-tenant denied events là tín hiệu quan trọng và nên được cảnh báo theo mức độ.

## 25. Đồng bộ thời gian và tương quan sự kiện

Điều tra cần dựng thứ tự sự kiện từ nhiều hệ thống. Nếu clock lệch, có thể hiểu sai rằng policy được sửa sau lần đọc secret hoặc một operation xảy ra trước khi token được cấp.

Nên:

- Ghi timestamp theo UTC và định dạng chuẩn.
- Giữ cả event time từ nguồn và ingest time ở collector.
- Đồng bộ thời gian qua nguồn tin cậy và theo dõi clock drift.
- Dùng request ID, trace ID, session ID hoặc correlation ID khi có thể.
- Giữ principal ID, resource ID, key ID/version nhất quán giữa hệ thống.
- Ghi source system và event schema version.

Không ghép event chỉ dựa trên timestamp gần nhau. Khi không có correlation ID, cần dùng nhiều thuộc tính và ghi rõ mức độ chắc chắn của quan hệ.

## 26. Retention và bảo vệ dữ liệu audit

Audit log có thể chứa danh tính, địa chỉ mạng, lịch làm việc và thông tin vận hành. Cần cân bằng khả năng điều tra với quyền riêng tư và nghĩa vụ lưu trữ.

Retention policy nên xác định:

- Thời hạn theo loại event và mức độ nhạy cảm.
- Yêu cầu pháp lý, hợp đồng và compliance.
- Cách giữ log cho incident/legal hold.
- Cách xóa an toàn sau khi hết retention.
- Quyền truy cập và export trong thời gian lưu.
- Mã hóa khi truyền/lưu và quản lý khóa bảo vệ log.
- Khả năng chứng minh log không bị sửa.

Không giữ mọi log vô thời hạn chỉ vì storage rẻ. Ngược lại, không đặt retention quá ngắn khiến tổ chức không thể điều tra sự cố được phát hiện muộn. Quyết định cần dựa trên threat model và yêu cầu áp dụng.

## 27. Bảo vệ audit pipeline khỏi bị vô hiệu hóa

Kẻ tấn công có thể tìm cách tắt audit, thay destination hoặc làm nghẽn event pipeline trước khi truy cập secret. Vì vậy, cần giám sát chính hệ thống audit:

- Alert khi audit logging bị disable hoặc cấu hình giảm event category.
- Alert khi collector ngừng nhận event hoặc event delay vượt ngưỡng.
- Theo dõi dropped event, queue backlog và authentication failure của collector.
- Ghi lại thay đổi destination, retention và access policy.
- Tách quyền quản trị audit khỏi quyền quản trị secret.
- Có buffer/retry bền vững để tránh mất event khi mạng gián đoạn.
- Kiểm tra định kỳ rằng event test xuất hiện đầy đủ trong immutable store và SIEM.

Nếu không thể ghi audit trong một thời gian, policy phải quyết định thao tác secret nhạy cảm có được tiếp tục hay không. Với thao tác đặc biệt quan trọng, có thể cần fail-closed; với hệ thống availability cao, cần buffer an toàn và cảnh báo ngay.

## 28. Incident response khi phát hiện truy cập secret bất thường

Khi có alert, đội phản ứng cần xác minh và giới hạn phạm vi:

1. Xác định principal, resource, version, operation và outcome.
2. Kiểm tra identity/session có hợp lệ và có dấu hiệu bị chiếm quyền không.
3. Dựng chuỗi policy change, grant, secret read và KMS/HSM operation.
4. Kiểm tra workload, host, deployment, source network và request trace.
5. Xác định secret có thể đã bị lộ hoặc chỉ có request bị từ chối.
6. Cô lập principal/workload hoặc thu hồi session khi cần.
7. Rotate/revoke secret và key bị ảnh hưởng theo thứ tự dependency.
8. Kiểm tra downstream system để tìm dấu hiệu credential được sử dụng.
9. Bảo toàn audit evidence và ngăn thay đổi/xóa log.
10. Ghi nhận phạm vi, timeline, quyết định và bằng chứng.

Nếu private key bị truy cập trái phép, cần xem xét certificate revocation, key replacement và dữ liệu/chữ ký bị ảnh hưởng. Nếu service password bị lộ, phải rotate ở cả secret manager lẫn hệ thống đích, rồi xác minh consumer đã chuyển sang version mới.

## 29. Kiểm thử audit control

Không nên chờ sự cố mới biết audit có hoạt động. Tạo các bài kiểm tra có kiểm soát:

| Test | Kết quả mong đợi |
|---|---|
| Workload được phép đọc secret | Có event success với principal/resource/version chính xác |
| Workload không có quyền đọc | Có event denied và policy reason |
| Human liệt kê nhiều secret | Có event list/search và cảnh báo theo policy |
| Thay đổi policy | Có before/after hoặc policy version và actor |
| Rotate secret | Có event start/success/failure và version liên quan |
| Disable/revoke | Có event actor, resource, approval và outcome |
| Break-glass | Có yêu cầu, approval, grant, access và revoke |
| Audit destination bị đổi | Có event và alert độc lập |
| Collector ngừng nhận event | Health alert hoặc event gap được phát hiện |
| Restore backup | Có event truy cập key/secret và restore approval |

Test phải dùng secret và identity thử. Không tạo truy cập trái phép vào production để thử detection nếu chưa có change/incident simulation được phê duyệt.

## 30. Ví dụ triển khai: Java service đọc secret từ vault

Một Java service lấy database credential từ secret manager khi khởi động. Thiết kế nên:

1. Workload xác thực bằng workload identity ngắn hạn.
2. Secret manager policy chỉ cho phép đọc đúng secret path và version cần thiết.
3. Secret manager phát audit event với principal, resource, version, operation và outcome.
4. Ứng dụng không ghi secret value vào log; nếu kết nối database thất bại, chỉ ghi mã lỗi và request ID.
5. Database audit ghi principal/database role và kết quả kết nối.
6. Nếu service cần dùng KMS để unwrap DEK, KMS audit ghi key ID và operation.
7. Correlation ID liên kết lần đọc secret, kết nối database và operation KMS khi kiến trúc hỗ trợ.
8. Security monitoring cảnh báo khi workload đọc secret ngoài scope hoặc đọc nhiều version bất thường.
9. Rotation tạo version mới, cập nhật workload và ghi nhận việc ngừng sử dụng version cũ.

Audit cho biết credential đã được cấp cho workload; database audit cho biết credential hoặc database identity đã được sử dụng để kết nối. Không ghi password vào application log để tạo mối liên kết này.

## 31. Checklist thiết kế Secret access audit

Trước khi đưa secret access audit vào production, hãy xác nhận:

- [ ] Đã có inventory secret, owner, purpose, environment và classification.
- [ ] Đã xác định nguồn audit của secret manager, IAM, KMS/HSM và workload.
- [ ] Ghi cả control-plane và data-plane events.
- [ ] Ghi success, denied, failed, list, export, rotate, revoke và destroy.
- [ ] Principal ID ổn định, phân biệt human với workload.
- [ ] Resource ID và version được ghi mà không ghi secret value.
- [ ] Event có timestamp UTC, operation, outcome, policy decision và request ID.
- [ ] Approval/ticket được liên kết với thao tác nhạy cảm.
- [ ] Raw event được redaction trước khi rời nguồn; không log token/password/key bytes.
- [ ] Audit store tách biệt, append-only/immutable và có phân quyền.
- [ ] Thay đổi logging, retention và destination cũng được audit.
- [ ] Pipeline có health monitoring, chống mất event và xử lý duplicate.
- [ ] SIEM có detection cho enumeration, denied burst, role escalation và truy cập bất thường.
- [ ] Break-glass có MFA, scope hẹp, thời hạn, approval và audit đầy đủ.
- [ ] Có access review định kỳ và xử lý principal không còn dùng.
- [ ] Retention phù hợp yêu cầu pháp lý, điều tra và quyền riêng tư.
- [ ] Có test cho allow, deny, policy change, rotation, revoke, restore và audit outage.
- [ ] Có incident response để cô lập principal, rotate secret và bảo toàn evidence.

## 32. Checklist điều tra một lần truy cập bất thường

Khi nhận alert, hãy xác nhận:

- [ ] Principal và session có đúng owner không?
- [ ] Workload/host/deployment có nằm trong change window không?
- [ ] Secret resource và version nào đã được truy cập?
- [ ] Request được allow, deny hay fail?
- [ ] Policy hoặc role có vừa thay đổi không?
- [ ] Có approval/ticket hợp lệ không?
- [ ] Có KMS/HSM operation hoặc downstream usage tương ứng không?
- [ ] Có truy cập list/export hoặc nhiều tenant/resource khác không?
- [ ] Có thể đã lộ secret value hay chỉ có request metadata?
- [ ] Đã revoke session/identity và rotate secret cần thiết chưa?
- [ ] Audit evidence đã được bảo toàn và timeline đã được dựng chưa?

Secret access audit biến hoạt động truy cập bí mật thành bằng chứng có thể kiểm tra và phân tích. Muốn audit có giá trị, cần nhận diện chính xác principal và resource, ghi cả allow lẫn deny, bao phủ thay đổi quyền và vòng đời secret, bảo vệ log khỏi sửa đổi, đồng thời không đưa secret value vào chính hệ thống log. Kết hợp audit của secret manager, IAM, KMS/HSM và workload sẽ giúp tổ chức phát hiện truy cập bất thường, điều tra có căn cứ và duy trì quyền truy cập theo nguyên tắc tối thiểu.
