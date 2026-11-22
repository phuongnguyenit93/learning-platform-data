# Chuyển yêu cầu tuân thủ thành kiểm soát kiến trúc

Yêu cầu tuân thủ thường bắt đầu từ luật, quy định ngành, hợp đồng khách hàng, chính sách nội bộ hoặc cam kết bảo mật. Những văn bản này thường dùng các khái niệm như bảo vệ dữ liệu, giới hạn truy cập, lưu giữ hồ sơ, kiểm toán, phục hồi và quản lý nhà cung cấp. Đội kiến trúc phải chuyển các khái niệm đó thành quyết định kỹ thuật có thể triển khai và kiểm chứng: dữ liệu được lưu ở đâu, ai được truy cập, khóa mã hóa do ai quản lý, log nào phải giữ, khi nào phải xóa, ai phê duyệt thay đổi và bằng chứng nào chứng minh kiểm soát đang hoạt động.

**Chuyển yêu cầu tuân thủ thành kiểm soát kiến trúc** là quá trình biến nghĩa vụ và mục tiêu quản trị thành control objective, control, ownership, evidence và quy trình vận hành xuyên suốt vòng đời hệ thống. Một yêu cầu chỉ được coi là xử lý tốt khi có thể trả lời: rủi ro nào cần giảm, hệ thống phải hành xử ra sao, thành phần nào thực thi, ai chịu trách nhiệm, bằng chứng được tạo ở đâu và điều gì xảy ra khi kiểm soát thất bại.

Tuân thủ không phải một tính năng có thể bật bằng một checkbox, cũng không đồng nghĩa với việc có chứng chỉ của nhà cung cấp cloud. Nhà cung cấp có thể cung cấp dịch vụ mã hóa, audit log, private networking hoặc vùng lưu trữ, nhưng khách hàng vẫn phải cấu hình, quản lý danh tính, phân loại dữ liệu, giới hạn quyền, vận hành quy trình và chứng minh kết quả trong phạm vi của mình.

Bài học thuộc phần **Quản trị và tuân thủ** của học phần thiết kế kiến trúc cloud. Trọng tâm là thiết kế kiểm soát khả thi, có chủ sở hữu và bằng chứng, đồng thời cân bằng bảo mật, độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và khả năng vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt nghĩa vụ, policy, control objective, control implementation và evidence.
- Phân tích yêu cầu pháp lý/hợp đồng thành yêu cầu kiến trúc có thể kiểm thử.
- Xác định phạm vi dữ liệu, hệ thống, môi trường, bên thứ ba và ranh giới trách nhiệm.
- Thiết kế kiểm soát cho identity, network, encryption, logging, retention, residency và SDLC.
- Lập ma trận traceability, control ownership, evidence và cadence kiểm tra.
- Dùng policy-as-code và compliance automation mà vẫn có quy trình xử lý ngoại lệ.
- Chuẩn bị audit evidence, quản lý finding và cải tiến kiểm soát liên tục.

## 1. Từ văn bản yêu cầu đến hành vi của hệ thống

Một văn bản có thể nói rằng dữ liệu cá nhân phải được bảo vệ khỏi truy cập trái phép. Câu đó định hướng mục tiêu, nhưng chưa đủ để triển khai. Kiến trúc cần diễn giải thành những câu hỏi cụ thể:

- Dữ liệu nào được xem là dữ liệu cá nhân?
- Người dùng, service và quản trị viên nào cần truy cập?
- Quyền nào được phép cho từng mục đích?
- Dữ liệu được truyền và lưu trữ ở đâu?
- Truy cập nào cần được ghi log và ai được xem log?
- Khi người dùng yêu cầu xóa, bản sao trong cache, warehouse và backup được xử lý thế nào?
- Làm sao chứng minh quyền đã bị thu hồi và dữ liệu đã được xử lý?

Luồng chuyển đổi cơ bản:

~~~mermaid
flowchart TD
    SRC["Luật / Quy định / Hợp đồng / Policy"] --> INTERP["Diễn giải phạm vi và nghĩa vụ"]
    INTERP --> RISK["Xác định rủi ro và control objective"]
    RISK --> CTRL["Thiết kế kiểm soát"]
    CTRL --> ARCH["Ánh xạ vào thành phần kiến trúc"]
    ARCH --> EVID["Tạo evidence và test"]
    EVID --> OPERATE["Vận hành, giám sát, xử lý finding"]
    OPERATE --> REVIEW["Review định kỳ / thay đổi phạm vi"]
    REVIEW --> INTERP
~~~

Quy trình này tạo một vòng lặp. Khi hệ thống thay đổi, nguồn dữ liệu mới được thêm hoặc nghĩa vụ thay đổi, cần xem lại control và bằng chứng có còn phù hợp hay không.

### Năm khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Requirement / obligation** | Điều tổ chức phải đáp ứng theo luật, hợp đồng hoặc policy | Chỉ người có thẩm quyền được xem hồ sơ khách hàng |
| **Control objective** | Kết quả/rủi ro cần được kiểm soát | Ngăn truy cập dữ liệu khách hàng ngoài mục đích được phép |
| **Control** | Cơ chế kỹ thuật hoặc quy trình làm giảm rủi ro | Role-based access, approval, audit và access review |
| **Implementation** | Thành phần và cấu hình cụ thể thực thi control | IAM role, policy, private endpoint, query audit |
| **Evidence** | Bằng chứng cho thấy control được thiết kế và vận hành | Policy version, access review record, log, test report |

Một control có thể hỗ trợ nhiều nghĩa vụ, và một nghĩa vụ có thể cần nhiều control. Không nên giả định một checkbox hoặc một screenshot chứng minh toàn bộ nghĩa vụ.

## 2. Xác định phạm vi tuân thủ trước khi thiết kế

Phạm vi xác định hệ thống, dữ liệu, người dùng, nhà cung cấp và quy trình nào thuộc đánh giá. Nếu scope sai, control có thể bị thiếu hoặc thiết kế quá rộng gây chi phí không cần thiết.

### 2.1. Phạm vi dữ liệu

Lập inventory cho:

- Loại dữ liệu: định danh, liên hệ, tài chính, sức khỏe, nội dung người dùng, thông tin xác thực và dữ liệu vận hành.
- Chủ thể dữ liệu và mục đích xử lý.
- Nguồn tạo dữ liệu và hệ thống sở hữu.
- Bản sao trong database, cache, object storage, data warehouse, log, export và backup.
- Đường truyền giữa service, region và nhà cung cấp.
- Thời gian lưu giữ, quy tắc archive và xóa.
- Mức độ nhạy cảm và hậu quả nếu rò rỉ hoặc sai lệch.

### 2.2. Phạm vi hệ thống và môi trường

Xác định ứng dụng production, staging, development, CI/CD, identity platform, monitoring, backup, support tooling và hệ thống bên thứ ba có thể truy cập dữ liệu. Môi trường test cũng có thể nằm trong scope nếu dùng dữ liệu thật hoặc bản sao có thể nhận dạng.

### 2.3. Phạm vi địa lý và bên thứ ba

Ghi nhận nơi dữ liệu được thu thập, xử lý, lưu, backup và hỗ trợ vận hành. Xác định cloud provider, SaaS, payment provider, email provider, managed database, observability và support subprocessors. Region được chọn trong console chưa chắc mô tả đầy đủ vị trí log, metadata, key, backup hoặc quyền support.

### 2.4. Ranh giới trách nhiệm

Với từng control, nêu ai:

- Thiết kế và phê duyệt.
- Cấu hình và triển khai.
- Vận hành thường xuyên.
- Theo dõi và xử lý vi phạm.
- Thu thập bằng chứng.
- Kiểm tra độc lập.

Tránh các mô tả mơ hồ như “IT chịu trách nhiệm bảo mật”. Hãy gán owner cụ thể theo vai trò: platform, application, security, privacy, data owner, procurement, legal/compliance và operations.

## 3. Phân tích yêu cầu thành control objective

Một yêu cầu thường có nhiều nghĩa vụ con. Hãy tách động từ, đối tượng, điều kiện, thời hạn và ngoại lệ.

Ví dụ câu “chỉ nhân sự được phê duyệt mới được truy cập dữ liệu nhạy cảm” có thể tách thành:

1. Có danh tính định danh riêng cho từng người và service.
2. Quyền truy cập dựa trên vai trò/mục đích công việc.
3. Quyền nhạy cảm cần phê duyệt trước khi cấp.
4. Quyền có thời hạn hoặc được review định kỳ.
5. Quyền bị thu hồi khi nhân sự đổi vai trò/nghỉ việc.
6. Truy cập và thay đổi quyền được audit.
7. Có test chứng minh người không có quyền bị từ chối.

### Cấu trúc control objective

Một objective tốt mô tả kết quả và ranh giới rõ:

~~~text
Control objective:
  Prevent unauthorized access to restricted customer data.

Scope:
  Production customer database, analytics export and support tooling.

Desired outcome:
  Only approved identities can access data for an authorized purpose.

Failure condition:
  Access is granted without approval, exceeds scope or is not traceable.
~~~

### Phân biệt control preventive, detective và corrective

| Loại | Vai trò | Ví dụ |
| --- | --- | --- |
| **Preventive** | Ngăn hành vi không mong muốn trước khi xảy ra | IAM deny-by-default, private network, deployment approval |
| **Detective** | Phát hiện hành vi hoặc cấu hình sai | Audit log alert, configuration scanner, access review |
| **Corrective** | Khắc phục hoặc giảm ảnh hưởng sau phát hiện | Revoke access, rotate key, restore, incident response |

Một rủi ro quan trọng thường cần kết hợp ba loại. Ví dụ private endpoint ngăn truy cập công khai, network audit phát hiện thay đổi ngoài policy, còn incident runbook thu hồi route sai và điều tra truy cập đã xảy ra.

## 4. Viết requirement có thể kiểm chứng

Yêu cầu kiến trúc phải đủ cụ thể để thiết kế và test. Tránh các câu không đo được như “hệ thống phải bảo mật”, “log đầy đủ” hoặc “backup thường xuyên”.

Mẫu chuyển đổi:

| Câu hỏi | Nội dung cần xác định |
| --- | --- |
| What | Đối tượng hoặc hành vi cần kiểm soát là gì? |
| Who | Ai hoặc hệ thống nào chịu trách nhiệm? |
| Where | Data/system/environment/region nào thuộc scope? |
| When | Kiểm tra trước, trong hay sau hoạt động? Tần suất nào? |
| How | Cơ chế kỹ thuật/quy trình nào thực thi? |
| Evidence | Bằng chứng nào cho thấy control hoạt động? |
| Failure | Điều gì xảy ra nếu control không đáp ứng? |

Ví dụ:

~~~text
Requirement:
  Restricted production database must not be reachable from the public internet.

Architecture control:
  Database has no public endpoint; access uses approved private network path.

Automated test:
  IaC policy rejects public database configuration.
  External connectivity test confirms no public route.

Operational evidence:
  Configuration scan result, change audit and exception register.

Owner:
  Platform engineering; Security reviews policy.
~~~

Ví dụ này chỉ minh họa cách viết control. Giá trị như tần suất scan, thời gian lưu log hoặc người phê duyệt phải được xác định từ policy thực tế.

## 5. Ma trận traceability: từ nghĩa vụ tới bằng chứng

Traceability matrix giúp nối nguồn yêu cầu với cấu hình và evidence. Đây là công cụ quan trọng khi audit, khi thay đổi hệ thống và khi chứng minh một control không bị bỏ sót.

### Mẫu ma trận

| Trường | Nội dung |
| --- | --- |
| Requirement ID | Mã nghĩa vụ/policy |
| Source and version | Văn bản nguồn, phiên bản/ngày hiệu lực |
| Applicability | Vì sao áp dụng hoặc không áp dụng |
| Data/system scope | Hệ thống, dataset, environment, region |
| Risk | Rủi ro nếu không đáp ứng |
| Control objective | Kết quả cần đạt |
| Control ID | Mã control nội bộ |
| Implementation | Thành phần, policy, cấu hình, quy trình |
| Owner | Người/đội chịu trách nhiệm |
| Test method | Cách kiểm tra thiết kế và vận hành |
| Evidence location | Nơi lưu evidence được kiểm soát |
| Frequency | Tần suất thực hiện |
| Exception/status | Trạng thái, ngoại lệ và ngày hết hạn |

### Ví dụ traceability

| Requirement | Control objective | Implementation | Evidence |
| --- | --- | --- | --- |
| Hạn chế truy cập dữ liệu khách hàng | Chỉ identity được duyệt mới truy cập | IAM role, database role, private endpoint | Role inventory, approval, access test, audit log |
| Bảo vệ dữ liệu lưu trữ | Bản sao dữ liệu thuộc scope được mã hóa | Encryption at rest, key policy | Resource configuration, key inventory, scan report |
| Theo dõi truy cập đặc quyền | Thao tác nhạy cảm có thể truy vết | Audit trail, central log, alert | Log sample, alert test, retention config |
| Xóa theo retention | Dữ liệu hết hạn được xử lý theo policy | Lifecycle job, deletion workflow, backup policy | Job run, deletion manifest, exception record |
| Khôi phục dịch vụ | Có thể phục hồi trong mục tiêu đã duyệt | Backup/PITR, DR runbook | Restore drill, RTO/RPO result, action items |

Một evidence có thể hỗ trợ nhiều control nhưng cần ghi chính xác scope và thời gian. Screenshot của cấu hình tại một thời điểm không chứng minh cấu hình luôn đúng hoặc đã hoạt động suốt cả kỳ audit.

## 6. Thiết kế kiểm soát danh tính và quyền truy cập

Identity và access management (IAM) thường là một trong những lớp kiểm soát quan trọng nhất vì người dùng, workload và quản trị viên đều truy cập qua danh tính.

### 6.1. Unique identity và service identity

- Mỗi người dùng quản trị có tài khoản cá nhân; không dùng chung tài khoản.
- Service dùng workload identity/role riêng thay vì chia sẻ credential giữa ứng dụng.
- Tài khoản break-glass được kiểm soát chặt, có MFA, lưu vết và review sau khi sử dụng.
- Credential dài hạn được giảm thiểu; secret có rotation và owner.
- Danh tính của CI/CD runner không có quyền rộng hơn pipeline cần.

### 6.2. Least privilege

Quyền chỉ đủ cho tác vụ và phạm vi cần thiết:

- Tách read, write, admin, export và key-management permissions.
- Tách production với non-production.
- Tách quyền deploy khỏi quyền đọc dữ liệu nhạy cảm.
- Tách quyền tạo snapshot khỏi quyền tải/export snapshot.
- Dùng resource scope, condition và session duration khi nền tảng hỗ trợ.

### 6.3. Joiner, mover, leaver

Quy trình IAM phải xử lý cả khi nhân sự bắt đầu, đổi nhóm và rời tổ chức. Thay đổi HR hoặc identity source cần kích hoạt cấp/điều chỉnh/thu hồi quyền. Quyền tạm thời và quyền vendor cần ngày hết hạn, sponsor và review.

### 6.4. Access review và privileged access

Lập danh sách quyền thực tế, owner và lý do. Review tập trung vào quyền nhạy cảm, stale account, quyền không dùng, quyền rộng và quyền ngoài giờ. Privileged access nên có approval, just-in-time elevation, MFA, session logging và giới hạn thời gian nếu phù hợp.

### Evidence

- Identity inventory và role/group mapping.
- Approval records và access review results.
- MFA/conditional access configuration.
- Privileged session log và break-glass review.
- Test truy cập được cho phép và bị từ chối.
- Bằng chứng thu hồi tài khoản/quyền sau thay đổi nhân sự.

## 7. Network controls và ranh giới tin cậy

Network control xác định đường nào được phép đi giữa user, application, database, control plane, vendor và internet.

### Các kiểm soát kiến trúc

- Public ingress đi qua gateway/load balancer/WAF theo mô hình được duyệt.
- Database, cache, broker và service nội bộ dùng private connectivity khi phù hợp.
- Security group/firewall theo least privilege; tránh dải nguồn/port quá rộng.
- Egress được kiểm soát để giảm nguy cơ exfiltration và truy cập endpoint không được phép.
- Phân đoạn production, staging, management và data plane.
- Admin access dùng đường truy cập chuyên biệt, có identity và audit.
- DNS, routing, private endpoint và service mesh policy được quản lý bằng code và review.
- TLS/mTLS được dùng theo threat model và khả năng của dịch vụ.

### Network segmentation không thay thế authorization

Một service nằm trong private subnet không có nghĩa mọi workload trong subnet được phép đọc mọi dữ liệu. Network policy giảm đường tiếp cận, còn application/IAM/database authorization quyết định hành động nào được phép. Nên dùng nhiều lớp kiểm soát độc lập.

### Evidence

Network architecture diagram, route/security policy, IaC scan report, firewall change approval, connectivity test và log thay đổi network. Cần có bằng chứng cho cả cấu hình mong muốn và trạng thái thực tế.

## 8. Bảo vệ dữ liệu: encryption, key và secret

Encryption là một control quan trọng nhưng phải gắn với key lifecycle, access control và data classification.

### Encryption at rest

Xác định resource nào cần mã hóa: database, object storage, disk, snapshot, backup, queue, log và export. Nhà cung cấp có thể bật encryption mặc định, nhưng khách hàng cần biết key ownership, quyền decrypt, rotation và ảnh hưởng khi key bị disable.

### Encryption in transit

Yêu cầu TLS cho đường client-to-service, service-to-service, database connection và đường truyền dữ liệu đến broker/storage khi phù hợp. Kiểm tra certificate validation, protocol version và hành vi khi certificate hết hạn.

### Key management

- Phân loại key theo dữ liệu và môi trường.
- Hạn chế ai có thể tạo, rotate, disable, schedule deletion hoặc grant decrypt.
- Separation of duties giữa quản trị key và quản trị dữ liệu nếu rủi ro yêu cầu.
- Theo dõi key usage và policy changes.
- Có quy trình xử lý key compromise và phục hồi backup.
- Trước khi rotate hoặc thu hồi key, kiểm tra snapshot/backup và DR dependency.

### Secret management

Secret nên lưu trong secret manager, không nhúng vào source, container image, CI log hoặc file cấu hình công khai. Workload identity có thể giảm nhu cầu secret tĩnh. Rotation cần phối hợp connection refresh, rollback và khả năng dùng đồng thời phiên bản cũ/mới trong giai đoạn chuyển tiếp.

### Evidence

Encryption inventory, KMS/key policy, key rotation records, TLS scan, secret access audit, exception list và test về resource không mã hóa.

## 9. Data governance: classification, residency, retention và deletion

Quản trị dữ liệu không dừng ở database chính. Một bản ghi có thể được sao chép sang cache, search index, event stream, data lake, observability và backup.

### 9.1. Classification

Định nghĩa các lớp dữ liệu và quy tắc xử lý. Ví dụ:

| Lớp minh họa | Đặc điểm | Kiểm soát có thể cần |
| --- | --- | --- |
| Public | Được phép công bố | Integrity, change approval, availability |
| Internal | Dùng trong nội bộ | Identity access, approved sharing, retention |
| Confidential | Dữ liệu kinh doanh/khách hàng cần bảo vệ | Encryption, least privilege, audit, controlled export |
| Restricted | Dữ liệu nhạy cảm cao hoặc có nghĩa vụ đặc biệt | Strong access controls, enhanced audit, masking, segregation, strict retention |

Tên lớp và tiêu chí phải theo policy tổ chức. Không gắn nhãn nhạy cảm chỉ dựa trên tên cột; cần hiểu ngữ cảnh, khả năng liên kết và mục đích sử dụng.

### 9.2. Data residency và cross-border flow

Residency có thể áp dụng cho dữ liệu chính, replica, backup, log, metadata, support access hoặc dữ liệu dẫn xuất. Cần lập data flow map:

- Nơi thu thập và nơi xử lý.
- Region lưu database/object storage.
- Region của backup/DR.
- Destination của log, telemetry, analytics và support tooling.
- Subprocessor và đường truyền ra nước ngoài.

Việc chọn region không tự chứng minh tuân thủ. Cần kiểm tra phạm vi dịch vụ, hợp đồng, control plane, backup behavior và điều kiện truy cập hỗ trợ.

### 9.3. Retention và deletion

Retention cần gắn với loại record, mục đích và nghĩa vụ. Không giữ mọi dữ liệu vô thời hạn vì storage rẻ. Cũng không xóa quá sớm khi cần phục vụ tranh chấp, kiểm toán hoặc legal hold.

Deletion workflow cần bao phủ primary store, replicas, cache, search, warehouse, export, backup và downstream consumer. Nếu backup không cho xóa từng record, cần quy định thời hạn backup hết hạn, kiểm soát restore để không làm dữ liệu đã xóa quay trở lại production và ghi nhận ngoại lệ hợp lệ.

### 9.4. Data minimization và masking

Chỉ thu thập và chia sẻ trường cần cho mục đích. Dùng masking, tokenization, pseudonymization hoặc aggregation cho môi trường phân tích/test. Dữ liệu giả lập vẫn cần kiểm tra để tránh vô tình chứa dữ liệu thật.

### Evidence

Data inventory, classification record, data flow map, retention schedule, deletion run logs, backup lifecycle config, data subject request evidence và access/export audit.

## 10. Logging, audit trail và khả năng truy vết

Logging giúp điều tra sự cố và chứng minh hoạt động, nhưng log cũng có thể chứa dữ liệu nhạy cảm và tạo thêm rủi ro.

### Phân biệt operational log và audit log

- **Operational log:** hỗ trợ debug, health và performance.
- **Audit log:** ghi nhận hành động cần truy vết, như truy cập dữ liệu nhạy cảm, thay đổi quyền, tạo/xóa key, thay đổi policy, export và thao tác quản trị.

Không phải log ứng dụng nào cũng là audit evidence. Audit log cần bảo vệ integrity, access, retention và tính đầy đủ phù hợp với mục đích.

### Nội dung audit event

Một audit record có thể ghi:

- Ai thực hiện (identity/service principal).
- Hành động gì (action).
- Tài nguyên nào (resource/scope).
- Khi nào (timestamp đồng bộ).
- Nguồn/đường truy cập (source/context).
- Kết quả (success/denied/error).
- Correlation/request ID.
- Approval/ticket reference nếu có.

Không ghi password, token, private key hoặc toàn bộ payload nhạy cảm. Mask dữ liệu theo policy.

### Bảo vệ audit trail

- Gửi log tới destination riêng có access control.
- Hạn chế quyền sửa/xóa log; có immutable/WORM option nếu yêu cầu.
- Mã hóa log và backup.
- Đồng bộ thời gian và giám sát mất log.
- Có alert khi logging pipeline ngừng hoặc audit event volume bất thường.
- Kiểm thử rằng thao tác nhạy cảm thực sự tạo event.

### Evidence

Audit configuration, sample event đã mask, retention proof, access list, integrity settings, alert test và log delivery health.

## 11. Secure SDLC và kiểm soát thay đổi

Tuân thủ phải đi theo vòng đời phát triển. Nếu chỉ review trước khi phát hành, cấu hình sai có thể xuất hiện ngay sau đó qua IaC, deployment pipeline hoặc thao tác console.

### Các gate trong SDLC

| Giai đoạn | Kiểm soát ví dụ | Evidence |
| --- | --- | --- |
| Plan/design | Threat model, data classification, architecture review | Review record, risk register, ADR |
| Code | Peer review, secret scan, SAST, dependency check | Pull request, scan results |
| Build | SBOM, signed artifact, provenance | Build attestation, artifact digest |
| Test | Security test, contract test, DAST phù hợp | Test report, remediation |
| Deploy | Approval, policy-as-code, least-privilege pipeline | Deployment record, policy result |
| Operate | Vulnerability monitoring, config drift, access review | Dashboard, scan, incident record |
| Retire | Revoke identity, delete data, archive required evidence | Decommission checklist, deletion record |

### Infrastructure as Code

IaC giúp kiểm soát cấu hình network, IAM, encryption, logging, backup và region qua code review và version history. Tuy nhiên, IaC chỉ mô tả trạng thái mong muốn. Cần kiểm tra drift và xác minh tài nguyên thực tế.

### Change management

Mỗi thay đổi có thể tác động control cần:

- Đánh giá control bị ảnh hưởng.
- Review/approval phù hợp mức rủi ro.
- Test trước khi deploy.
- Có rollback/recovery plan.
- Ghi lại artifact/version và người thực hiện.
- Kiểm tra trạng thái sau deploy.

Emergency change có thể dùng quy trình rút gọn nhưng phải có audit và retrospective review, không tạo lối bỏ qua vĩnh viễn.

## 12. Policy-as-code và compliance automation

Policy-as-code biểu diễn quy tắc kiến trúc thành điều kiện có thể kiểm tra tự động. Nó hữu ích với cấu hình lặp lại như không public database, bắt buộc encryption, hạn chế region, yêu cầu tag, logging và backup.

### Pipeline kiểm soát tham khảo

~~~mermaid
flowchart TD
    PR["Pull request / IaC change"] --> LINT["Lint + validate"]
    LINT --> SEC["Security / secret / dependency scan"]
    SEC --> POLICY["Policy-as-code evaluation"]
    POLICY --> GATE{"Compliant?"}
    GATE -- "Yes" --> APPROVE["Required review / approval"]
    APPROVE --> DEPLOY["Deploy"]
    DEPLOY --> DRIFT["Runtime configuration scan"]
    DRIFT --> REPORT["Evidence and compliance dashboard"]
    GATE -- "No" --> FIX["Fix or request documented exception"]
    FIX --> PR
~~~

### Ví dụ policy logic

~~~text
deny if resource.type == "managed_database"
     and resource.public_access == true

deny if resource.environment == "production"
     and resource.encryption_at_rest != true

require if resource.data_classification in ["confidential", "restricted"]
     then resource.owner is not empty
      and resource.audit_enabled == true
~~~

Đây là pseudocode để diễn tả ý tưởng, không phải cú pháp của một engine cụ thể. Policy thật phải hiểu resource type, trạng thái mặc định, scope, exception và cách kiểm tra runtime.

### IaC scan và runtime scan

- **Pre-deploy scan:** phát hiện cấu hình sai trước khi tạo tài nguyên.
- **Runtime scan:** kiểm tra tài nguyên đang chạy, kể cả thay đổi ngoài pipeline.
- **Drift detection:** so sánh trạng thái thực tế với trạng thái được quản lý.
- **Continuous control monitoring:** đánh giá lại control theo lịch hoặc khi có event.

Một pipeline xanh không đảm bảo production mãi tuân thủ. Người dùng có thể thay đổi console, service có thể tự thay đổi default, policy có thể được cập nhật hoặc resource mới được tạo ngoài IaC.

## 13. Evidence management và chuẩn bị audit

Audit evidence cần đủ tin cậy, đúng phạm vi, đúng thời kỳ và có thể truy xuất. Một tài liệu policy nói rằng MFA được bật không chứng minh mọi tài khoản production đều áp dụng MFA trong kỳ kiểm toán.

### Thu thập evidence

Với mỗi control, định nghĩa:

- Evidence source (cloud API, SIEM, ticketing, CI/CD, HR/IAM hoặc test).
- Owner và người xác nhận.
- Thời kỳ evidence bao phủ.
- Tính toàn vẹn và quyền truy cập.
- Tần suất thu thập.
- Cách lưu trữ, retention và mã hóa.

### Design effectiveness và operating effectiveness

- **Design effectiveness:** control được thiết kế có thể giảm rủi ro trong phạm vi đã định không?
- **Operating effectiveness:** control đã thực sự hoạt động nhất quán trong một khoảng thời gian chưa?

Ví dụ, policy access review có thiết kế tốt nhưng không có record review trong quý thì chưa có bằng chứng operating effectiveness.

### Evidence package

Một package cho control có thể chứa:

1. Control description và owner.
2. Scope/resource inventory.
3. Policy/configuration snapshot có timestamp/version.
4. Access/approval/change records trong kỳ.
5. Test result và sample log đã mask.
6. Finding, exception và remediation status.
7. Người xác nhận và thời gian xác nhận.

Không tạo evidence thủ công chỉ để phục vụ audit nếu hệ thống có thể thu thập tự động từ nguồn gốc. Nếu phải chụp ảnh màn hình hoặc export, ghi source, thời điểm và cách đảm bảo không bị chỉnh sửa sai lệch.

## 14. Quản lý finding, exception và risk acceptance

Không phải mọi control đều có thể đáp ứng ngay. Có thể có ngoại lệ do giới hạn dịch vụ, dependency cũ, migration hoặc yêu cầu nghiệp vụ. Ngoại lệ cần được quản lý như rủi ro có chủ sở hữu, không phải một ghi chú không thời hạn.

### Exception record

Một ngoại lệ nên ghi:

- Control ID và resource/system bị ảnh hưởng.
- Lý do không đáp ứng và bằng chứng.
- Mức rủi ro, khả năng và tác động.
- Biện pháp bù (compensating controls).
- Owner, người có thẩm quyền chấp nhận.
- Thời hạn, ngày hết hạn và điều kiện thu hồi.
- Kế hoạch remediation/migration.
- Cadence review và trigger tái đánh giá.

### Risk acceptance

Chấp nhận rủi ro phải ở đúng cấp thẩm quyền và trong giới hạn policy. Đội kỹ thuật không tự chấp nhận thay cho business owner hoặc risk owner nếu policy yêu cầu phê duyệt cấp cao hơn. Không dùng risk acceptance để hợp thức hóa vi phạm pháp luật hoặc hành vi bị cấm.

### Remediation lifecycle

1. Ghi nhận finding và kiểm tra phạm vi.
2. Đánh giá mức độ nghiêm trọng và ảnh hưởng.
3. Chọn fix, mitigation hoặc exception hợp lệ.
4. Gán owner và deadline.
5. Triển khai thay đổi và thu evidence.
6. Kiểm tra độc lập hoặc re-test.
7. Đóng finding khi có bằng chứng; cập nhật risk register.

### Compensating control

Nếu không thể bật một control gốc, biện pháp bù cần giảm cùng rủi ro với hiệu lực có thể giải thích. Ví dụ hệ thống cũ chưa hỗ trợ MFA có thể được đặt sau privileged access gateway, chỉ cho phép network quản trị, ghi session và giới hạn tài khoản trong thời gian migration. Biện pháp bù không tự động tương đương với control gốc; cần đánh giá và phê duyệt.

## 15. Shared responsibility với cloud provider và SaaS

Một dịch vụ cloud có thể có chứng nhận, báo cáo audit và control environment riêng. Tổ chức sử dụng dịch vụ vẫn phải xác định phần nào được provider kiểm soát và phần nào phải do khách hàng thực hiện.

### Cách đánh giá provider

- Xác định dịch vụ/SKU/region cụ thể nằm trong phạm vi báo cáo nào.
- Xem thời kỳ báo cáo và các carve-out/subservice organizations.
- Đọc customer responsibilities/user entity controls (nếu có).
- Kiểm tra data residency, subprocessors và support access.
- Xem incident notification, vulnerability handling và SLA.
- Đánh giá backup, deletion, encryption, key ownership và export.
- Kiểm tra khả năng cung cấp evidence khi audit hoặc điều tra.
- Xác định quy trình offboarding và xóa dữ liệu khi kết thúc hợp đồng.

Chứng nhận của provider không tự chứng minh ứng dụng của khách hàng tuân thủ. Ví dụ provider có encryption at rest nhưng resource có thể được tạo với cấu hình sai; provider có audit service nhưng customer có thể chưa bật hoặc chưa centralize log.

### RACI mẫu

| Hoạt động | Cloud provider | Platform team | Application/data owner | Security/compliance |
| --- | --- | --- | --- | --- |
| Bảo vệ datacenter/hardware | R/A | I | I | C |
| Cấu hình IAM workload | C | R | R | A/C |
| Schema/data classification | I | C | R/A | C |
| Private network policy | C | R/A | C | C |
| Backup service capability | R | R | C | C |
| Retention/restore testing | C | R | R | A/C |
| Audit log enablement/use | C | R | R | A/C |
| Risk exception | I | C | R | A (theo authority policy) |

RACI phải điều chỉnh theo tổ chức, hợp đồng và mô hình dịch vụ. Một hạng mục có thể có nhiều bên thực hiện nhưng chỉ nên có một accountable owner cho quyết định cuối.

## 16. Đưa compliance vào architecture decision và design review

Compliance không nên xuất hiện lần đầu ở cuối dự án. Nó cần tham gia khi xác định context, data flow, technology choices và operating model.

### Những điểm cần review

- Service có xử lý loại dữ liệu nào và mục đích gì?
- Region, tenancy và data flow có đáp ứng policy không?
- Identity, privilege và network boundary có least privilege không?
- Encryption, key ownership, secrets và audit có đầy đủ?
- Backup, restore, retention, deletion và DR có phù hợp?
- Vendor/subprocessor có được đánh giá?
- Logging có bảo vệ privacy và hỗ trợ evidence?
- IaC/CI/CD có policy gate và drift detection?
- Control có owner, test, evidence và exception path?

### Gắn requirement vào ADR

Mỗi ADR có thể ghi:

~~~text
Decision:
  Use private managed database in approved region.

Compliance drivers:
  Restricted customer records; approved data residency.

Controls:
  Private endpoint, workload identity, encryption key policy,
  audit logging, backup retention and restore exercise.

Evidence:
  IaC plan, runtime configuration scan, IAM review,
  audit log sample and restore test.

Trade-offs:
  Higher network setup effort; cross-region recovery constrained.

Owner / review trigger:
  Platform + data owner; review when region, data class or provider changes.
~~~

ADR không thay thế legal interpretation hoặc control register, nhưng nối quyết định kiến trúc với nghĩa vụ và trade-off để người review hiểu tại sao lựa chọn được đưa ra.

## 17. Compliance automation và continuous monitoring

Nhiều kiểm soát có thể được kiểm tra định kỳ hoặc theo event:

- Resource không có owner tag.
- Database public hoặc thiếu encryption.
- IAM policy có quyền wildcard không hợp lệ.
- Audit log bị tắt hoặc delivery pipeline có gap.
- Backup vượt retention policy.
- Resource được tạo tại region không được duyệt.
- Certificate, secret hoặc key sắp hết hạn.
- Vulnerability vượt severity/age threshold.
- Exception đã hết hạn nhưng chưa được xử lý.

### Continuous control monitoring

~~~mermaid
flowchart LR
    CLOUD["Cloud configuration / APIs"] --> COLLECT["Inventory + evidence collectors"]
    CI["CI/CD + IaC"] --> COLLECT
    IAM["Identity and access systems"] --> COLLECT
    LOG["Audit / SIEM"] --> COLLECT
    COLLECT --> EVAL["Control evaluation"]
    EVAL --> DASH["Compliance dashboard"]
    EVAL --> FIND["Finding / ticket"]
    FIND --> OWNER["Control owner"]
    OWNER --> FIX["Remediate / exception"]
    FIX --> VERIFY["Re-test and close"]
    VERIFY --> DASH
~~~

Automation cần xử lý false positive, scope và freshness. Một scanner không thấy resource có thể do thiếu quyền đọc hoặc collector lỗi; không nên đánh dấu compliant khi evidence không đầy đủ. Trạng thái UNKNOWN hoặc NOT EVALUATED phải được phân biệt với PASS.

### Maturity levels

Có thể đánh giá tiến bộ theo các mức:

1. **Manual:** checklist và evidence thu thập thủ công.
2. **Repeatable:** quy trình, owner và cadence ổn định.
3. **Automated:** scan, policy test và evidence collection tự động.
4. **Continuous:** drift/finding được phát hiện và xử lý trong thời gian xác định.
5. **Measured:** hiệu quả control, false positive, remediation time và residual risk được đo để cải tiến.

Không cần tự động hóa mọi thứ ngay từ đầu. Ưu tiên control có rủi ro cao, tần suất thay đổi lớn và bằng chứng dễ thu thập.

## 18. Những sai lầm thường gặp

**Sao chép nguyên văn điều khoản thành checklist kỹ thuật.** Câu chữ pháp lý cần được diễn giải theo phạm vi, mục đích và rủi ro trước khi thiết kế.

**Mặc định chứng chỉ của cloud provider bao phủ ứng dụng.** Control tại workload, IAM, data lifecycle và quy trình khách hàng vẫn cần triển khai.

**Không xác định applicability và scope.** Hệ thống, log, backup hoặc SaaS phụ trợ có thể bị bỏ sót.

**Chỉ viết policy mà không có implementation.** Tài liệu yêu cầu MFA không bật MFA; policy retention không có lifecycle job.

**Chỉ có implementation mà không có evidence.** Không thể chứng minh control đang hoạt động trong kỳ cần đánh giá.

**Dùng một screenshot làm bằng chứng lâu dài.** Snapshot cấu hình không chứng minh operating effectiveness hoặc phạm vi đầy đủ.

**Không có owner và cadence.** Control không được review, finding không được xử lý và exception tồn tại vô thời hạn.

**Dùng policy-as-code nhưng không kiểm tra runtime drift.** Thay đổi console hoặc resource ngoài pipeline có thể phá control sau deploy.

**Đánh dấu UNKNOWN là compliant.** Thiếu evidence phải được xử lý như một trạng thái cần điều tra, không phải PASS.

**Giữ log mọi thứ mà không bảo vệ log.** Audit trail có thể trở thành nơi tập trung dữ liệu nhạy cảm và credential.

**Retention chỉ áp dụng cho database chính.** Cache, analytics, export, backup và downstream copy cũng có lifecycle.

**Chấp nhận ngoại lệ không có expiry.** Rủi ro tạm thời có thể trở thành cấu hình vĩnh viễn.

**Dùng compensating control mà không đánh giá hiệu lực.** Biện pháp bù cần chứng minh nó giảm rủi ro trong phạm vi tương đương.

**Để security review ở cuối dự án.** Thay đổi region, identity hoặc storage sau khi build có thể rất tốn kém.

## 19. Bài thực hành: chuyển yêu cầu tuân thủ thành kiến trúc kiểm soát

**Bối cảnh giả định:** Một nền tảng SaaS đặt lịch phục vụ doanh nghiệp ở nhiều thị trường. Ứng dụng gồm API gateway, Booking Service, Customer Service, Payment Service, managed relational database, object storage, cache, event broker, data warehouse, CI/CD và hệ thống giám sát. Dữ liệu gồm thông tin định danh/liên hệ khách hàng, lịch hẹn, trạng thái thanh toán và log truy cập. Một số khách hàng yêu cầu dữ liệu chính ở region cụ thể; nhóm hỗ trợ cần quyền truy cập có kiểm soát để xử lý sự cố. Đây là kịch bản mô phỏng, không đại diện cho kết luận pháp lý của một quốc gia hoặc ngành cụ thể.

### Nhiệm vụ 1 — Xác định scope và data flow

Vẽ luồng dữ liệu từ client tới API, service, database, cache, event broker, warehouse, log, backup và provider. Đánh dấu:

- Data owner và classification.
- Processing purpose và consumer.
- Region của primary, replica, backup, log và support.
- Bên thứ ba/subprocessor.
- Retention, deletion và export path.

### Nhiệm vụ 2 — Phân tích nghĩa vụ và control objective

Nhận các yêu cầu giả định:

1. Chỉ người được duyệt có thể truy cập hồ sơ khách hàng.
2. Database production không được public.
3. Dữ liệu nhạy cảm phải được mã hóa khi lưu và truyền.
4. Truy cập đặc quyền phải được ghi audit và review.
5. Dữ liệu được lưu theo retention schedule và có quy trình xóa.
6. Dịch vụ cần có khả năng phục hồi theo RTO/RPO đã được owner xác nhận.

Với mỗi yêu cầu, viết control objective, risk, scope, control type, owner và test method.

### Nhiệm vụ 3 — Thiết kế implementation

Đề xuất IAM, private network, TLS, key management, audit log, data masking, backup/restore, retention lifecycle, deletion workflow và CI/CD policy gate. Chỉ rõ phần provider quản lý và phần khách hàng phải cấu hình/kiểm chứng.

### Nhiệm vụ 4 — Xây traceability matrix

Tạo mã requirement/control; nối source, risk, implementation, resource, evidence, owner, frequency và exception. Xác định evidence nào tự động thu thập được và evidence nào cần xác nhận thủ công.

### Nhiệm vụ 5 — Thiết kế continuous compliance

Viết policy logic cho database public, encryption missing, audit disabled, region disallowed và owner tag missing. Quy định kết quả PASS/FAIL/UNKNOWN, ticket routing, severity, remediation deadline và re-test.

### Nhiệm vụ 6 — Xử lý ngoại lệ

Một integration cũ chưa hỗ trợ private connectivity trong 60 ngày. Lập exception record gồm rủi ro, scope, biện pháp bù, owner, approver, expiry, remediation plan và trigger thu hồi. Đánh giá xem có thể tiếp tục xử lý dữ liệu nhạy cảm không.

### Nhiệm vụ 7 — Chuẩn bị audit package

Chọn một control và tạo package gồm policy, configuration snapshot, inventory, approval, access review, test report, audit event mẫu và finding. Phân biệt evidence chứng minh design effectiveness với operating effectiveness.

### Deliverables

| Đầu ra | Nội dung |
| --- | --- |
| Data/system scope map | Data flow, region, vendor, environment và classification |
| Requirement register | Nguồn, version, applicability, obligation và risk |
| Control register | Objective, preventive/detective/corrective, owner và frequency |
| Traceability matrix | Requirement → control → implementation → evidence |
| Architecture package | IAM, network, encryption, logging, retention và DR controls |
| Policy-as-code | Rule, CI gate, runtime scan và trạng thái UNKNOWN |
| Exception register | Risk, compensating controls, approval và expiry |
| Audit evidence package | Design/operating evidence và finding status |
| ADR | Quyết định, trade-off, giả định và review trigger |

## 20. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho governance và compliance |
| --- | --- |
| **Operational Excellence** | Mỗi control có owner, runbook, cadence, evidence source, finding workflow và review trigger không? |
| **Security** | Identity, least privilege, segmentation, encryption, key, audit, data lifecycle và vendor access được kiểm soát không? |
| **Reliability** | Backup/restore, DR, log delivery, key recovery, control-plane dependency và incident process đáp ứng mục tiêu không? |
| **Performance Efficiency** | Logging, encryption, policy evaluation và monitoring có ảnh hưởng latency/capacity; có thể kiểm soát overhead không? |
| **Cost Optimization** | Evidence retention, SIEM ingestion, KMS, audit, scanning, backup và compliance tooling có dự toán không? |
| **Sustainability** | Có tránh thu thập log thừa, giữ dữ liệu quá hạn và chạy scan/pipeline trùng lặp không cần thiết không? |

## 21. Checklist trước khi đưa kiểm soát tuân thủ vào production

- [ ] Nguồn yêu cầu, phiên bản, phạm vi áp dụng và người diễn giải được ghi nhận.
- [ ] Data/system/environment/region/vendor scope đã được lập bản đồ.
- [ ] Nghĩa vụ được tách thành risk và control objective có thể kiểm chứng.
- [ ] Mỗi control có ID, owner, loại control, implementation, test và evidence.
- [ ] Ma trận traceability nối requirement → control → resource → evidence.
- [ ] Shared responsibility với cloud provider/SaaS được xác minh theo dịch vụ và hợp đồng cụ thể.
- [ ] IAM, service identity, least privilege, access review và privileged access có bằng chứng.
- [ ] Network, private access, egress và TLS được kiểm tra cả ở IaC lẫn runtime.
- [ ] Encryption at rest/in transit, key ownership, rotation và recovery được xác định.
- [ ] Classification, residency, retention, deletion và backup lifecycle bao phủ mọi bản sao.
- [ ] Audit trail có integrity, access control, retention và alert khi mất log.
- [ ] Secure SDLC, change approval, IaC scan và runtime drift detection được thiết lập.
- [ ] Policy-as-code phân biệt PASS, FAIL và UNKNOWN; có cách xử lý false positive.
- [ ] Evidence đủ scope/thời kỳ và chứng minh cả design lẫn operating effectiveness.
- [ ] Finding/exception có risk owner, approval, compensating control, expiry và remediation.
- [ ] Có quy trình audit request, evidence export và bảo vệ evidence.
- [ ] Đã thử access denial, encryption checks, restore, deletion và incident process.
- [ ] Control được review khi data flow, provider, region, version hoặc mục đích xử lý thay đổi.
- [ ] Chi phí compliance tooling, logging, evidence retention và vận hành được tính.

Chuyển yêu cầu tuân thủ thành kiểm soát kiến trúc là quá trình nối nghĩa vụ với hành vi hệ thống có thể quan sát và kiểm chứng. Bắt đầu bằng scope và rủi ro, xác định control objective, thiết kế implementation cùng owner, rồi thu evidence và giám sát trong vận hành. IAM, network, encryption, data lifecycle, audit, SDLC và policy automation là các lớp thường gặp, nhưng chỉ có giá trị khi phù hợp nghĩa vụ thực tế và có bằng chứng vận hành. Một kiến trúc có khả năng tuân thủ lâu dài phải quản lý cả thay đổi, ngoại lệ, nhà cung cấp và phục hồi; không chỉ đạt một lần ở thời điểm go-live.
