# Chủ quyền, vị trí và chuyển dữ liệu xuyên biên giới

## 1. Vì sao vị trí dữ liệu là quyết định kiến trúc?

Ứng dụng cloud thường phân phối compute và storage ở nhiều khu vực để giảm độ trễ, tăng khả năng phục hồi và mở rộng quy mô. Tuy nhiên, dữ liệu của một khách hàng có thể đi qua nhiều nơi: được thu thập ở một quốc gia, xử lý ở region khác, sao lưu sang region thứ ba, hiển thị trong dashboard của đội hỗ trợ ở nước khác và được nhà cung cấp hoặc nhà thầu phụ truy cập khi vận hành.

Vì vậy, câu hỏi “database đang nằm ở region nào?” chưa đủ để xác định dữ liệu được quản lý phù hợp. Phải hiểu toàn bộ vòng đời và đường đi của dữ liệu, gồm bản chính, replica, snapshot, backup, log, telemetry, cache, file export, dữ liệu dẫn xuất và quyền truy cập quản trị.

Ba khái niệm thường được dùng:

- **Data residency (vị trí lưu trữ dữ liệu):** dữ liệu được lưu ở đâu về mặt địa lý hoặc nơi đặt hạ tầng.
- **Data sovereignty (chủ quyền dữ liệu):** dữ liệu chịu sự điều chỉnh, quyền tài phán hoặc quyền kiểm soát của quốc gia/vùng lãnh thổ nào theo bối cảnh pháp lý và hợp đồng.
- **Data localization (nội địa hóa dữ liệu):** yêu cầu hoặc chính sách buộc một số loại dữ liệu phải được lưu trữ, xử lý hoặc duy trì bản sao trong phạm vi lãnh thổ xác định.

Các khái niệm liên quan nhưng không đồng nghĩa. Một database đặt tại quốc gia A vẫn có thể chịu yêu cầu pháp lý khác nếu tổ chức, chủ thể dữ liệu, hoạt động xử lý hoặc nhà cung cấp thuộc phạm vi tài phán khác. Ngược lại, yêu cầu lưu dữ liệu tại một nước không nhất thiết cấm mọi hình thức truy cập hoặc chuyển dữ liệu ra nước ngoài; phạm vi phụ thuộc quy định và bối cảnh cụ thể.

Trong module **CLOUD_ARCHITECTURE**, quyết định về chủ quyền và vị trí dữ liệu cần được chuyển thành kiến trúc thực tế: region placement, replication, backup, network path, identity, key management, telemetry, support access và hợp đồng với nhà cung cấp. Mục tiêu là đáp ứng yêu cầu nghiệp vụ và pháp lý với độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành có thể kiểm soát theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt sovereignty, residency, localization và cross-border transfer.
- Xác định dữ liệu nào thuộc phạm vi hạn chế và ở giai đoạn nào có thể được chuyển.
- Lập bản đồ luồng dữ liệu từ thu thập đến backup, support và xóa.
- Thiết kế placement, replication, backup, logging và key control theo vùng.
- Đánh giá quyền truy cập từ xa, nhà cung cấp và subprocessor.
- Phối hợp với pháp chế, privacy, security và procurement để xác minh điều kiện chuyển dữ liệu.
- Đưa các yêu cầu về vị trí dữ liệu thành guardrail, policy-as-code và bằng chứng kiểm toán.

## 2. Phân biệt residency, sovereignty và localization

| Khái niệm | Trọng tâm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Data residency | Nơi dữ liệu được lưu hoặc xử lý | Database, backup, log và replica đang ở quốc gia/region nào? |
| Data sovereignty | Quyền tài phán và quyền kiểm soát | Luật/quyền nào có thể áp dụng với dữ liệu, tổ chức và nhà cung cấp? |
| Data localization | Nghĩa vụ giới hạn dữ liệu trong lãnh thổ | Loại dữ liệu nào phải lưu, xử lý hoặc giữ bản sao nội địa? |
| Cross-border transfer | Việc truyền/truy cập dữ liệu qua biên giới | Dữ liệu hoặc quyền truy cập có đi từ một jurisdiction sang jurisdiction khác không? |

Ví dụ, một tổ chức có thể lưu database chính tại Việt Nam nhưng dùng đội support ở một quốc gia khác để xem bản ghi lỗi có chứa thông tin khách hàng. Dù byte dữ liệu chính không được sao chép sang máy chủ của đội support, hoạt động truy cập từ xa vẫn có thể tạo ra vấn đề về transfer/access theo quy định áp dụng và hợp đồng. Cần đánh giá chính xác với pháp chế và privacy, không kết luận chỉ dựa vào vị trí disk.

### 2.1. Xác định phạm vi dữ liệu

Không phải mọi dữ liệu đều có cùng yêu cầu:

- Dữ liệu cá nhân và dữ liệu nhạy cảm.
- Dữ liệu tài chính, thanh toán hoặc giao dịch.
- Dữ liệu sức khỏe, sinh trắc học hoặc dữ liệu có phân loại đặc biệt.
- Hồ sơ khách hàng doanh nghiệp, bí mật kinh doanh và intellectual property.
- Dữ liệu cơ quan nhà nước hoặc dữ liệu theo hợp đồng công.
- Metadata, identifier, log và dữ liệu dẫn xuất có thể liên kết tới cá nhân/tổ chức.
- Dữ liệu công khai, dữ liệu tổng hợp và dữ liệu đã được đánh giá là không thể nhận diện.

Classification cần theo field và khả năng liên kết. Một log có IP, account ID, timestamp và URL có thể chứa dữ liệu nhạy cảm dù không có tên hoặc địa chỉ.

### 2.2. Phân biệt nơi lưu, nơi xử lý và nơi truy cập

Đối với mỗi dataset, lập ít nhất ba góc nhìn:

1. **At rest:** bản chính, replica, snapshot, backup, cache và file export được lưu ở đâu?
2. **In transit/in process:** dữ liệu được truyền và xử lý qua region, service, network hoặc runtime nào?
3. **Access location:** người dùng, administrator, support engineer, subprocessor hoặc automation từ quốc gia nào có thể truy cập?

Một số yêu cầu chỉ liên quan lưu trữ; một số quy định có thể áp dụng đến việc xử lý, disclosure hoặc access. Đội kiến trúc cần chuyển câu chữ chính sách/pháp lý thành các ràng buộc cụ thể cho ba góc nhìn trên.

## 3. Data flow mapping: biết dữ liệu đi đâu

Trước khi chọn region hoặc bật replication, hãy xây dựng bản đồ dữ liệu. Không có data flow inventory thì không thể chứng minh một dataset thực sự ở trong phạm vi được phép.

### 3.1. Mô hình luồng dữ liệu điển hình

~~~mermaid
flowchart LR
    User["Người dùng / thiết bị"] --> Edge["CDN / WAF / API edge"]
    Edge --> App["Ứng dụng region A"]
    App --> DB["Database region A"]
    DB --> Replica["Replica region B"]
    DB --> Backup["Backup region C"]
    App --> Logs["Logs / traces / metrics"]
    Logs --> Observability["Observability platform"]
    DB --> Lake["Data lake / warehouse"]
    Support["Support / operator"] -. "Remote access" .-> App
    Vendor["Cloud provider / subprocessor"] -. "Operational access" .-> DB
~~~

Sơ đồ này chỉ là ví dụ. Bản đồ thực tế phải ghi rõ giao thức, identity, purpose, data class, region, retention, encryption và owner tại từng luồng.

### 3.2. Data flow register

| Thành phần/luồng | Dữ liệu | Nơi đi / nơi đến | Câu hỏi governance |
| --- | --- | --- | --- |
| Client → API | Profile, identifier, nội dung request | Quốc gia người dùng → ingress region | Có thu thập quá mức? TLS và edge log có lưu body không? |
| API → Database | Transaction và profile | Application region → DB region | Primary placement có phù hợp? |
| Database → Replica | WAL/change stream hoặc record | Region A → Region B | Có được phép replicate? Sync hay async? |
| Database → Backup | Snapshot/log archive | Region A → bucket/vault khác | Backup location, retention và key ở đâu? |
| App → Observability | Log, trace, metric, crash dump | Runtime → telemetry service | Có PII/secrets? Telemetry được xử lý ở region nào? |
| Data lake → BI | Curated/aggregate data | Data zone → warehouse/BI region | Có masking và purpose control? |
| Support → Production | Query, session hoặc screen share | Nhân viên ở quốc gia khác | Remote access có được phép, ghi audit và giới hạn không? |
| Provider/subprocessor | Metadata hoặc nội dung khách hàng | Cloud/service provider | DPA, subprocessor list, support location và transfer terms? |

### 3.3. Những bản sao hay bị bỏ sót

- Read replica, cross-region replica và disaster recovery copy.
- Snapshot, point-in-time recovery log, backup catalog và export.
- Cache, CDN origin/shield, search index và materialized view.
- Application logs, trace spans, crash dump, analytics event và alert payload.
- Notebook local storage, query result cache, temporary spill file và developer export.
- Ticket support, email trao đổi, chat attachment và screen recording.
- Test/staging environment, synthetic dataset được tạo từ production.
- Subprocessor, managed support, security monitoring và anti-fraud service.

Một bản sao “tạm thời” vẫn có thể chứa dữ liệu và tạo nghĩa vụ bảo vệ. Inventory cần ghi cả dữ liệu transient nếu nó đi qua boundary hoặc được giữ trong một khoảng thời gian đáng kể.

### 3.4. Thuộc tính cần ghi cho mỗi flow

Mỗi luồng nên có source, destination, data subject/owner, field/classification, purpose, protocol, direction, location/jurisdiction, identity, encryption, retention, downstream copy, transfer basis/approval reference và evidence. Nếu destination hoặc support access chưa rõ, coi đây là khoảng trống cần đóng trước khi triển khai dữ liệu restricted.

## 4. Đánh giá yêu cầu pháp lý và hợp đồng trước khi thiết kế

Kiến trúc sư cloud không nên tự diễn giải một điều khoản pháp lý thành “được” hoặc “cấm” khi chưa có đủ bối cảnh. Vai trò của kiến trúc là cung cấp dữ kiện kỹ thuật chính xác để legal/privacy/security đánh giá, sau đó chuyển kết luận đã được phê duyệt thành cấu hình và kiểm soát có thể kiểm chứng.

### 4.1. Các nguồn yêu cầu

- Quy định tại quốc gia nơi tổ chức thành lập, hoạt động hoặc cung cấp dịch vụ.
- Quy định tại nơi chủ thể dữ liệu cư trú hoặc nơi dữ liệu được thu thập/xử lý.
- Quy định ngành như tài chính, y tế, viễn thông hoặc dịch vụ công.
- Hợp đồng khách hàng, data processing agreement (DPA), confidentiality terms và security addendum.
- Chính sách nội bộ về data classification, retention, acceptable use và access.
- Yêu cầu kiểm toán/chứng nhận mà tổ chức cam kết.
- Điều khoản cloud provider, managed service và subprocessor.

Một dataset có thể chịu nhiều nguồn yêu cầu cùng lúc. Không chỉ dựa vào quốc gia của cloud region để kết luận áp dụng pháp luật nào.

### 4.2. Quy trình assessment

1. Xác định data controller/processor/owner và các bên nhận dữ liệu theo vai trò trong bối cảnh cụ thể.
2. Phân loại dữ liệu, chủ thể, purpose, volume, sensitivity và mức độ nhận diện.
3. Lập data flow map gồm storage, processing, remote access, backup và downstream.
4. Liệt kê jurisdiction của source, destination, organization, provider và support personnel.
5. Đối chiếu quy định, DPA, transfer terms, localization và retention với legal/privacy.
6. Xác định điều kiện cho phép, biện pháp bổ sung, thông báo/consent hoặc hạn chế.
7. Ghi quyết định, owner, thời hạn, phạm vi dữ liệu và bằng chứng phê duyệt.
8. Chuyển quyết định thành architecture requirements, policy-as-code và kiểm thử.
9. Đánh giá lại khi thay provider, region, subprocessor, data purpose hoặc loại dữ liệu.

### 4.3. Regulatory requirements matrix

| Câu hỏi | Ví dụ bằng chứng cần thu thập | Đầu ra kiến trúc |
| --- | --- | --- |
| Dataset nào bị điều chỉnh? | Data inventory, schema, classification | Scope tag và zone placement |
| Có yêu cầu nội địa hóa không? | Điều khoản luật/contract đã được legal xác nhận | Allowed region list, deny cross-border replication |
| Có thể chuyển ra nước ngoài theo điều kiện nào? | Transfer mechanism/assessment/contract approval tương ứng | Approved flow và transfer gate |
| Ai có thể truy cập từ xa? | Provider support terms, staff location, access logs | JIT access, support approval, customer-managed controls |
| Retention và deletion ra sao? | Records schedule, legal hold, privacy policy | Lifecycle, immutable retention và deletion workflow |
| Có yêu cầu thông báo sự cố? | Incident clause/regulatory duty | Data location inventory, notification runbook |
| Có được dùng subprocessor? | DPA, list, change notification và objection right nếu có | Vendor allowlist và subprocessor register |

Không ghi nội dung diễn giải luật thành một cấu hình cố định nếu yêu cầu còn phụ thuộc facts. Hãy lưu reference tới legal decision và người chịu trách nhiệm, không biến nhận định kỹ thuật thành legal advice.

## 5. Kiến trúc placement theo jurisdiction

Khi đã biết nơi dữ liệu được phép lưu/xử lý, kiến trúc sư có thể định nghĩa placement strategy theo data class và tenant.

### 5.1. Single-region data boundary

Với dataset bị hạn chế nghiêm ngặt, tổ chức có thể đặt primary, replica, backup và processing trong một region hoặc phạm vi địa lý được phê duyệt. Điều này đơn giản hóa data residency nhưng có thể giảm lựa chọn DR, tăng latency cho người dùng xa và cần kế hoạch bảo vệ dữ liệu trong cùng boundary.

Không mặc định một region duy nhất đồng nghĩa không có transfer. Provider support, global control plane, telemetry và administrative access vẫn cần được đánh giá.

### 5.2. Regional cell / data partition theo jurisdiction

Một mô hình thường dùng là triển khai cell độc lập theo jurisdiction. Request được route đến cell tương ứng; data store, encryption key, backup và operational access được giới hạn theo policy.

~~~mermaid
flowchart TB
    Global["Global entry / DNS / WAF"] --> Router["Tenant and jurisdiction router"]
    Router --> CellA["Regional cell A"]
    Router --> CellB["Regional cell B"]
    subgraph A["Jurisdiction A boundary"]
        CellA --> AppA["Application A"]
        AppA --> DBA[("Database A")]
        AppA --> ObjA["Object storage A"]
        DBA --> BkpA["Backup A"]
    end
    subgraph B["Jurisdiction B boundary"]
        CellB --> AppB["Application B"]
        AppB --> DBB[("Database B")]
        AppB --> ObjB["Object storage B"]
        DBB --> BkpB["Backup B"]
    end
~~~

Mô hình cell giảm nguy cơ trộn dữ liệu giữa tenant/jurisdiction và giới hạn blast radius. Đổi lại, nó nhân đôi hạ tầng, deployment, monitoring, support và có thể làm analytics toàn cầu phức tạp hơn.

### 5.3. Shared control plane, regional data plane

Một số nền tảng dùng control plane toàn cầu để quản lý deployment, policy hoặc metadata, trong khi data plane xử lý dữ liệu tại region. Cần đánh giá control plane có lưu tên tenant, query metadata, resource identifier, IP, log hay secret không; dữ liệu nào có thể nhìn thấy từ nhân sự vận hành toàn cầu.

Nếu metadata cũng nhạy cảm, cần giới hạn field, pseudonymize, phân tách tenant identifier và áp dụng retention. Không gọi control plane là “không chứa customer data” nếu nó lưu log hoặc metadata có thể liên kết.

### 5.4. Global service và regional restriction

Một dịch vụ dùng chung toàn cầu có thể chỉ nhận dữ liệu đã giảm thiểu hoặc tổng hợp. Dữ liệu thô bị hạn chế ở regional cell; aggregate chỉ được xuất sau privacy review, ngưỡng kích thước nhóm và phê duyệt purpose. Đây là cách tách analytics toàn cầu khỏi bản ghi định danh khu vực, nhưng không tự loại bỏ rủi ro tái nhận diện.

## 6. Replication, backup và disaster recovery dưới ràng buộc vị trí

DR đa khu vực có thể xung đột với yêu cầu localization. Thiết kế copy toàn bộ sang region dự phòng chỉ hợp lệ khi dataset được phép đi tới đó và các điều kiện transfer đã được phê duyệt.

### 6.1. Phân loại dữ liệu theo replication policy

| Loại dữ liệu | Replication có thể chọn | Điều kiện cần xác minh |
| --- | --- | --- |
| Restricted/localized | Replica trong boundary được phép | AZ/region có đủ resilience và policy rõ |
| Confidential được phép transfer | Cross-region có kiểm soát | Transfer approval, encryption, access và retention |
| Public | Replication/CDN rộng theo mục đích | Integrity, cache invalidation và nguồn chính thức |
| Pseudonymized/aggregate | Có thể chuyển theo assessment | Khả năng re-identification và mapping key có tách biệt không |
| Backup/log | Theo policy riêng, không mặc định theo primary | Backup location, support access, retention và immutable copy |

### 6.2. DR trong cùng jurisdiction

Nếu dữ liệu phải giữ trong một quốc gia, có thể dùng nhiều AZ hoặc nhiều region nội địa nếu provider cung cấp và legal/security chấp thuận. Nếu chỉ có một region đủ điều kiện, cần xem xét backup offline/immutable, cross-account vault trong cùng boundary, restore test, spare capacity và khả năng phục hồi từ lỗi logical.

Không nên hy sinh khả năng khôi phục mà không có business risk acceptance. Nếu localization làm RTO/RPO khó đạt, ghi rõ khoảng trống, phương án thay thế và người phê duyệt.

### 6.3. Backup và archive

Backup có thể chứa toàn bộ dữ liệu gốc, kể cả field đã bị masking trong curated dataset. Cần policy riêng về:

- Vị trí lưu và vị trí key.
- Mã hóa, immutability và quyền restore/delete.
- Retention, legal hold và expiry.
- Bản sao catalog, metadata, log archive và database WAL.
- Access của provider support/managed backup service.
- Xử lý deletion request đối với bản backup còn trong retention.

Một snapshot ở region khác vẫn là dữ liệu được sao chép qua biên giới nếu nó chứa dữ liệu thuộc phạm vi hạn chế.

### 6.4. Crypto-erasure và key boundary

Customer-managed key hoặc regional KMS key có thể hỗ trợ kiểm soát quyền giải mã theo boundary. Tuy nhiên, key đặt ở region nội địa không tự chứng minh data residency, và xóa key không đảm bảo xóa plaintext export/cache. Phải lập bản đồ encryption context, key usage, replicas, backups và quyền của operator.

## 7. Cross-border transfer và remote access

Chuyển dữ liệu xuyên biên giới có thể diễn ra qua nhiều cơ chế: copy object/database, replication, API call, telemetry export, support session hoặc truy cập trực tiếp từ nhân sự ở nước ngoài. Phạm vi transfer và điều kiện hợp lệ cần được legal/privacy xác định theo dữ liệu, chủ thể, destination và quy định áp dụng.

### 7.1. Phân loại loại luồng chuyển

| Hình thức | Ví dụ | Kiểm soát kiến trúc |
| --- | --- | --- |
| Bulk transfer | Export database, copy bucket, migration | Approval, encryption, checksum, transfer log, destination controls |
| Continuous replication | Database replica, object replication, event stream | Region allowlist, scope filter, lag monitor, key separation |
| API/service-to-service | Gửi profile hoặc transaction sang processor | Purpose, schema minimization, TLS, service identity, recipient contract |
| Remote interactive access | Support engineer mở console hoặc query | JIT access, MFA, approval, session recording/audit và masking |
| Telemetry transfer | Log, trace, crash dump gửi về global observability | Scrubbing, field allowlist, regional collector, retention |
| Derived data | Aggregate, pseudonymous feature hoặc report | Re-identification assessment, query controls và purpose limitation |

Không chỉ dữ liệu được lưu vĩnh viễn mới cần đánh giá. Payload truyền qua API, màn hình support, log hoặc query result cũng có thể tiết lộ thông tin.

### 7.2. Transfer assessment và safeguards

Tùy khuôn khổ pháp lý và hợp đồng áp dụng, việc chuyển dữ liệu có thể đòi hỏi một cơ chế pháp lý, đánh giá tác động, điều khoản hợp đồng, thông báo/consent, biện pháp kỹ thuật bổ sung hoặc điều kiện khác. Kiến trúc sư cần:

1. Xác định exporter, importer, data subject, dataset và purpose.
2. Xác định country/jurisdiction của từng bên và service endpoint.
3. Đối chiếu transfer mechanism đã được legal/privacy phê duyệt cho tình huống này.
4. Mô tả dữ liệu có thể truy cập, thời hạn, subprocessor và onward transfer.
5. Chọn safeguards như encryption, pseudonymization, minimization, access restriction, logging và key control.
6. Ghi bằng chứng assessment, approval, hợp đồng và ngày review.
7. Kiểm thử rằng kỹ thuật thực thi đúng scope đã được duyệt.

Encryption hoặc pseudonymization có thể giảm rủi ro nhưng không tự tạo ra căn cứ pháp lý cho transfer. Không dùng một checklist kỹ thuật chung thay thế legal assessment.

### 7.3. Remote access cũng là một luồng dữ liệu

Support engineer có thể đọc dữ liệu qua query, console, screen share hoặc remote desktop. Cần xác định:

- Nhân sự truy cập từ đâu và có thuộc provider/subprocessor không.
- Họ có thể xem raw value, query result, export hoặc download không.
- Nội dung session có được ghi vào ticket, log hoặc recording ở region khác không.
- Có thể masking theo role và chỉ cấp quyền tạm thời cho incident cụ thể không.
- Ai phê duyệt, ai giám sát và evidence được giữ ở đâu?

Mẫu kiểm soát thường dùng là just-in-time (JIT) access, MFA, ticket/incident reference, time-bound role, command/session audit, field masking và approval cho break-glass. Đường support khẩn cấp phải được kiểm thử trước disaster; nếu quy trình phê duyệt không khả dụng khi sự cố, cần một break-glass path có kiểm soát và audit.

### 7.4. Telemetry, log và trace

Log thường vô tình chứa:

- URL query string, header, cookie, authorization token.
- Email, phone, account ID, IP và device identifier.
- Request/response body hoặc stack trace có dữ liệu khách hàng.
- Database query literal, SQL parameter và object key.
- Screenshot, crash dump, memory dump và trace baggage.

Thiết kế telemetry theo allowlist field và schema, không dựa vào việc “developer sẽ nhớ không log PII”. Redact ở nguồn, dùng correlation ID không chứa định danh trực tiếp, phân vùng collector theo jurisdiction, giới hạn sampling/export và có test phát hiện secret/PII. Với trace, tránh nhét payload vào span attribute.

## 8. Cloud provider và subprocessor governance

Cloud provider có thể cung cấp nhiều region nhưng không phải mọi dịch vụ, tính năng support, control plane, billing, abuse monitoring hoặc backup đều có cùng khả năng chọn vị trí dữ liệu. Phải đánh giá theo từng dịch vụ và hợp đồng, không suy từ region của VM/database.

### 8.1. Vendor due diligence

| Chủ đề | Câu hỏi cần làm rõ |
| --- | --- |
| Region availability | Dịch vụ cụ thể có mặt ở region được phép không? Có giới hạn feature? |
| Data location | Primary, replica, metadata, backup, logs và support data nằm ở đâu? |
| Administrative access | Nhân sự provider/subprocessor ở đâu có thể truy cập? Theo điều kiện nào? |
| Subprocessor | Danh sách, quốc gia, dịch vụ, thông báo thay đổi và onward transfer? |
| Encryption/key | Provider-managed hay customer-managed key? Provider support có thể giải mã trong tình huống nào? |
| Deletion/retention | Dữ liệu và backup được xóa khi nào? Có exception hoặc legal hold? |
| Incident | Thời gian và kênh thông báo, evidence, cooperation và audit right? |
| Portability | Có thể export dữ liệu/metadata và chuyển provider khi chấm dứt? |
| Assurance | Có báo cáo kiểm toán/chứng nhận phù hợp scope và thời hạn? |

Chứng nhận hoặc báo cáo kiểm toán của provider là bằng chứng hỗ trợ, không tự chứng minh kiến trúc cụ thể của khách hàng đáp ứng mọi nghĩa vụ. Cần đối chiếu service scope, shared responsibility và cấu hình thực tế.

### 8.2. Shared responsibility

Provider có thể bảo vệ hạ tầng vật lý và một phần dịch vụ; khách hàng vẫn chịu trách nhiệm cấu hình region, IAM, data classification, access, key, retention, export và ứng dụng. Với managed service, trách nhiệm vận hành có thể khác self-managed nhưng không đồng nghĩa trách nhiệm về purpose, dataset và recipient biến mất.

Lập ma trận:

| Kiểm soát | Provider | Customer |
| --- | --- | --- |
| Physical facility | Thiết kế và vận hành theo dịch vụ | Đánh giá assurance và lựa chọn region |
| Region/replica configuration | Cung cấp khả năng và giới hạn | Chọn location, enable/disable replication |
| IAM/data access | Cung cấp cơ chế | Thiết kế role, policy, review quyền |
| Encryption | Cung cấp encryption/KMS options | Chọn key model, scope và lifecycle |
| Retention/deletion | Thực hiện theo feature/contract | Đặt policy, kiểm tra bản sao và workflow |
| Support access | Chính sách nhân sự và vận hành provider | Chọn support plan, approval và dữ liệu cung cấp |
| Incident response | Thông báo và hỗ trợ theo hợp đồng | Điều phối khách hàng, assessment và nghĩa vụ báo cáo |

Ma trận thực tế cần được hoàn thiện theo từng dịch vụ, hợp đồng và mô hình shared responsibility.

### 8.3. Change management của subprocessor

Một nhà cung cấp có thể thay đổi subprocessor, vị trí support hoặc đường telemetry theo thời gian. Cần:

- Theo dõi thông báo thay đổi và thời hạn phản hồi.
- Đánh giá lại transfer/data flow khi subprocessor mới tham gia.
- Cập nhật vendor register, DPA và architecture decision.
- Xem xét quyền phản đối/chấm dứt theo điều khoản hợp đồng.
- Đảm bảo migration/exit plan nếu thay đổi làm mất điều kiện chấp nhận.

## 9. Policy-as-code và guardrail cho vị trí dữ liệu

Yêu cầu residency chỉ đáng tin khi có thể kiểm soát lúc tạo resource và trong thời gian vận hành. Tài liệu policy nên chuyển thành rule tự động, nhưng luôn có owner và exception process.

### 9.1. Region allowlist

Ví dụ một policy logic:

~~~text
IF dataset.classification == "restricted"
THEN
  allowed_regions = approved_regions_for(dataset.jurisdiction)
  deny_replication_to_any_unapproved_region
  require_customer_managed_key_if_policy_demands
  require_backup_location_in_approved_boundary
  require_access_role_with_matching_jurisdiction
END
~~~

Đây là pseudo-policy minh họa, không phải cú pháp của cloud provider. Khi triển khai, phải map sang cloud organization policy, IaC validation, admission controller, resource policy và runtime monitoring tương ứng.

### 9.2. Các lớp thực thi

- **Preventive:** chặn tạo bucket/database/network/resource ở region không được phép.
- **Detective:** quét resource, replica, backup và IAM để phát hiện drift.
- **Corrective:** tự động quarantine hoặc mở ticket; chỉ tự xóa/chuyển dữ liệu khi hành động an toàn và đã được phê duyệt.
- **Evidence:** ghi policy version, decision, resource, principal, timestamp và exception.

Không nên chỉ dựa vào tag do developer tự khai. Kết hợp identity, account/project, dataset metadata, destination và kiểm tra runtime.

### 9.3. Infrastructure as code

IaC có thể khai báo region, encryption key, backup vault, replication destination, logging endpoint và access policy. Pipeline nên kiểm tra:

1. Region thuộc allowlist của dataset.
2. Không có replication/export tới destination chưa duyệt.
3. Encryption và key policy đáp ứng classification.
4. Logging/telemetry không bật raw payload ngoài boundary.
5. Backup lifecycle và retention phù hợp.
6. Support roles có time limit và scope.

Config drift có thể xuất hiện qua console/manual change hoặc dịch vụ được tạo ngoài pipeline. Cần periodic scan và quy trình xử lý drift.

### 9.4. Exception management

Nếu cần exception, yêu cầu phải có business justification, dataset/scope, destination, duration, compensating controls, risk owner, legal/security approval và expiry date. Exception tự hết hạn và được review; không dùng wildcard region hoặc exception vô thời hạn để né guardrail.

## 10. Retention, deletion và data subject request xuyên biên giới

Chủ quyền dữ liệu không chỉ liên quan nơi lưu mà còn cách dữ liệu được giữ, sao chép, cung cấp và xóa. Một yêu cầu xóa hoặc hạn chế xử lý có thể ảnh hưởng tới nhiều region, backup, processor và dataset dẫn xuất.

### 10.1. Retention register

Mỗi dataset nên có:

- Purpose và business owner.
- Classification và jurisdiction.
- Retention duration/trigger, nguồn policy và ngày review.
- Legal hold hoặc exception hiện hành.
- Primary/replica/backup/archive locations.
- Deletion method và downstream notification.
- Owner chịu trách nhiệm xác nhận hết hạn.

Retention của database, event log, object version, snapshot, backup và telemetry có thể khác nhau. Không nên dùng một TTL toàn cục cho tất cả bản sao nếu yêu cầu khác nhau.

### 10.2. Deletion propagation

~~~mermaid
flowchart TB
    Request["Verified request / retention expiry"] --> Policy["Policy and legal hold check"]
    Policy --> Inventory["Lineage + location inventory"]
    Inventory --> Primary["Primary data"]
    Inventory --> Replica["Replicas / secondary regions"]
    Inventory --> Derived["Warehouse / index / feature"]
    Inventory --> Export["Exports / processors / cache"]
    Inventory --> Backup["Backup / archive schedule"]
    Primary --> Verify["Verification and evidence"]
    Replica --> Verify
    Derived --> Verify
    Export --> Verify
    Backup --> Verify
~~~

Workflow cần phân biệt accepted, in progress, completed, exception/held và failed. Không thông báo đã xóa hoàn tất nếu backup immutable vẫn đang được giữ theo retention policy. Khi backup cũ được restore, cần áp dụng deletion ledger hoặc tombstone trước khi đưa dataset trở lại hoạt động.

### 10.3. Data portability và exit plan

Khả năng chuyển dữ liệu khỏi provider là một phần của governance. Cần xác định:

- Export format, schema, metadata, key mapping và lineage.
- Transfer destination có được phép tiếp nhận dataset không.
- Egress cost, bandwidth, thời gian và giới hạn API.
- Encryption in transit, integrity/checksum và chain of custody.
- Cách chuyển key/secret an toàn hoặc re-encrypt tại destination.
- Cách dừng replication, thu hồi identity và xóa bản sao tại provider cũ.
- Bằng chứng deletion/termination, backup expiry và subprocessor offboarding.

Exit plan nên được kiểm tra ở mức đại diện. Một hợp đồng có quyền export nhưng không có quy trình thực tế hoặc key recovery vẫn có thể dẫn tới lock-in vận hành.

## 11. Incident response và yêu cầu cung cấp dữ liệu

Incident liên quan dữ liệu có thể phát sinh từ disclosure trái phép, credential compromise, transfer nhầm region, subprocessor thay đổi, bucket public hoặc log lộ PII. Quy trình cần kết hợp security, legal/privacy, cloud operations và business owner.

### 11.1. Phát hiện và khoanh vùng

1. Xác định dataset, field, chủ thể, tenant và jurisdiction bị ảnh hưởng.
2. Xác định dữ liệu đã được lưu, truy cập, tải xuống hoặc onward transfer ở đâu.
3. Bảo toàn audit log, cloud trail, session record và evidence với access hạn chế.
4. Thu hồi/giới hạn credential hoặc đường transfer có nguy cơ, tránh phá hủy evidence.
5. Xác định provider/subprocessor liên quan và kích hoạt kênh incident theo hợp đồng.
6. Legal/privacy xác định nghĩa vụ thông báo, thời hạn và cơ quan/người nhận theo quy định áp dụng.
7. Khắc phục policy, rotate key/token, xóa bản sao hoặc cô lập theo kế hoạch được duyệt.
8. Ghi timeline, impact, root cause, corrective action và kiểm tra hiệu lực.

### 11.2. Yêu cầu cung cấp dữ liệu từ cơ quan hoặc bên thứ ba

Yêu cầu pháp lý từ cơ quan nhà nước, tòa án hoặc bên thứ ba cần được xử lý theo quy trình legal của tổ chức và điều khoản provider. Đội kỹ thuật không tự quyết định cung cấp dữ liệu chỉ dựa trên email hoặc ticket.

Cần xác minh tính xác thực, thẩm quyền, phạm vi, jurisdiction, loại dữ liệu, thời hạn, nghĩa vụ thông báo và khả năng phản đối/giới hạn theo quy trình. Ghi audit người nhận, dữ liệu được cung cấp, approval và chain of custody. Provider có thể có quy trình riêng để thông báo khách hàng hoặc xử lý yêu cầu trực tiếp; phải đọc đúng hợp đồng/dịch vụ.

### 11.3. Evidence và audit readiness

Có thể cần chứng minh:

- Resource được tạo tại region nào và ai thay đổi location.
- Replica, backup, log và telemetry có destination nào.
- Ai có quyền access/export và những lần truy cập thực tế.
- Key nào bảo vệ dữ liệu, ai dùng key và policy tại thời điểm đó.
- Transfer nào đã được phê duyệt và theo purpose nào.
- Retention/deletion được thực thi ra sao, ngoại lệ nào còn hiệu lực.
- Provider/subprocessor nào tham gia và hợp đồng nào áp dụng.

Evidence nên có owner, timestamp, policy/version và integrity protection. Tránh lưu lại payload nhạy cảm chỉ để chứng minh tuân thủ.

## 12. Các mẫu kiến trúc theo mức hạn chế dữ liệu

Không có một mô hình duy nhất cho mọi tổ chức. Chọn pattern theo classification, residency, RTO/RPO, locality, analytics requirement và năng lực vận hành.

| Pattern | Đặc điểm | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Single jurisdiction deployment | Data plane, backup và processing trong một boundary | Dễ kiểm soát vị trí; ít luồng chuyển | DR và capacity có thể hạn chế; global latency |
| Regional cells | Mỗi jurisdiction có cell dữ liệu riêng | Isolation, local scaling và policy độc lập | Nhân đôi vận hành; đồng bộ cấu hình khó |
| Global control plane + regional data plane | Quản trị chung, dữ liệu xử lý theo vùng | Chuẩn hóa platform và giữ data locality | Metadata/control plane vẫn cần đánh giá |
| Local raw + global aggregate | Raw data giữ tại vùng; chỉ xuất aggregate/feature đã duyệt | Hỗ trợ analytics rộng mà hạn chế raw transfer | Re-identification, metric consistency và purpose cần kiểm soát |
| Federated query | Query chạy gần dữ liệu, gửi kết quả về consumer | Có thể tránh copy raw dataset | Query result vẫn có thể nhạy cảm; network và performance phức tạp |
| Clean room / controlled collaboration | Các bên truy vấn/chia sẻ theo policy và điều kiện giới hạn | Giảm trao đổi raw file trực tiếp | Không tự loại bỏ mọi rủi ro; rule và participant phải được quản trị |

### 12.1. Federated query không đồng nghĩa không có transfer

Query engine có thể chạy gần data source nhưng kết quả, count, metadata, query plan hoặc error message vẫn truyền về nơi gọi. Phải xem output grain, small-cell suppression, query budget, logs và caching.

### 12.2. Regional aggregate cần ngưỡng và mục đích

Nếu regional cell gửi doanh thu tổng hợp sang global warehouse, cần đánh giá liệu group có quá nhỏ hoặc có thể kết hợp với dữ liệu công khai để suy ra một khách hàng. Có thể áp minimum group size, suppression, noise hoặc giới hạn query theo policy. Ngưỡng cụ thể phải được lựa chọn theo risk assessment và mục đích, không copy một con số chung cho mọi dataset.

### 12.3. Không route dựa vào IP một cách mù quáng

Geo-IP hoặc DNS locality có thể hỗ trợ route tới region gần, nhưng không chứng minh jurisdiction, residency hoặc tenant ownership. Người dùng di chuyển, VPN, proxy và edge cache làm vị trí IP khác với data jurisdiction. Hãy route theo tenant/account policy hoặc authoritative metadata đã xác minh; dùng network location như một tín hiệu phụ.

## 13. Well-Architected: đánh đổi của chủ quyền và vị trí dữ liệu

| Góc nhìn | Quyết định kiến trúc | Đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Data flow register, owner, vendor register, policy-as-code, audit và exception workflow | Governance đầy đủ cần metadata kỷ luật và cập nhật liên tục |
| **Security / Bảo mật** | Regional boundary, least privilege, encryption, JIT support và telemetry scrubbing | Isolation tăng độ an toàn nhưng làm support/debug phức tạp hơn |
| **Reliability / Độ tin cậy** | DR trong boundary, backup độc lập, restore test và regional cell | Localization có thể giới hạn lựa chọn region và tăng chi phí dự phòng |
| **Performance Efficiency / Hiệu quả hiệu năng** | Local data processing, cache/aggregate và federated query | Giảm transfer nhưng tăng chi phí compute tại nhiều vùng và orchestration |
| **Cost Optimization / Tối ưu chi phí** | Chia tier, giảm data copy, chọn service theo locality | Multi-cell, backup nội địa và egress restriction có thể tăng TCO |
| **Sustainability / Bền vững** | Data minimization, retention và giảm replica không cần thiết | Ít bản sao giảm footprint nhưng phải giữ đủ resilience và compliance |

Một architecture decision record nên ghi requirement, dataset scope, jurisdiction, allowed destinations, transfer mechanism/approval, support path, backup/DR, cost, exception và ngày review. Khi provider thêm region/service hoặc tổ chức thay đổi purpose, ADR cần được xem xét lại.

## 14. Bài thực hành: thiết kế nền tảng cloud cho nhiều jurisdiction

Một công ty cung cấp nền tảng thương mại điện tử cho khách hàng ở hai quốc gia. Ứng dụng có customer profile, order, payment reference, catalog, clickstream, logs và dashboard doanh thu. Database chính đang ở một region; đội support làm việc từ quốc gia thứ hai; analytics warehouse dùng dịch vụ global; backup được sao chép sang region dự phòng. Tổ chức đang xem xét mở rộng sang một quốc gia mới có yêu cầu về vị trí dữ liệu khác.

**Yêu cầu bài làm:**

1. Phân loại từng dataset và field; xác định dữ liệu cá nhân, nhạy cảm, bí mật kinh doanh và metadata có thể liên kết.
2. Vẽ data flow map gồm primary, replica, backup, log, trace, cache, support access, warehouse và subprocessor.
3. Lập bảng jurisdiction source/destination/processing/access cho từng flow.
4. Xác định những câu hỏi phải chuyển cho legal/privacy để đánh giá localization và transfer; không tự giả định một yêu cầu áp dụng cho mọi dữ liệu.
5. Đề xuất regional cell hoặc single-boundary design cho dataset hạn chế; giải thích control plane và global service có thể nhìn thấy metadata nào.
6. Xác định replication/backup/DR strategy trong phạm vi được phê duyệt; nêu tác động tới RTO/RPO và cost.
7. Thiết kế remote support với JIT, MFA, field masking, approval và audit; xử lý tình huống incident khẩn cấp.
8. Đề xuất telemetry schema/allowlist để tránh log và trace gửi dữ liệu nhạy cảm ra ngoài boundary.
9. Xây dựng region allowlist, IaC validation, drift detection và exception expiry.
10. Thiết kế retention/deletion/exit workflow cho replica, backup, analytics và subprocessor.
11. Đưa ra vendor due diligence checklist và bằng chứng cần thu thập từ cloud provider.
12. Viết ADR so sánh regional cells, global aggregate và federated query theo governance, performance, reliability và TCO.

### Gợi ý đánh giá

Một bài làm tốt phân biệt rõ data at rest, processing và remote access. Không chỉ kiểm tra region của database mà còn chỉ ra backup, KMS, telemetry, support và subprocessor. Mỗi cross-border flow có destination, purpose, owner, approval và safeguards cụ thể.

Thiết kế cần cho thấy cách route tenant tới đúng cell, cách ngăn replica/backup bị tạo ở region ngoài allowlist và cách phát hiện drift. Analytics toàn cầu chỉ nhận dữ liệu đã được đánh giá và giảm thiểu; aggregate không tự động được coi là anonymous. Phải nêu RTO/RPO và cost tăng thêm khi giới hạn DR trong jurisdiction.

## 15. Checklist trước khi triển khai dữ liệu xuyên biên giới

- [ ] Có data inventory, owner, classification và purpose cho từng dataset.
- [ ] Phân biệt residency, sovereignty, localization và remote access/transfer.
- [ ] Data flow map bao gồm primary, replica, backup, snapshot, cache, log, trace, export và subprocessor.
- [ ] Location của storage, processing, control plane, support và key management đã được xác minh.
- [ ] Legal/privacy đã xác nhận quy định, contract và transfer mechanism áp dụng cho từng flow.
- [ ] Dữ liệu được minimize; raw/restricted field không đi vào telemetry/analytics không cần thiết.
- [ ] Region placement và tenant routing dựa trên jurisdiction policy đã xác minh.
- [ ] Replica, backup và DR destination thuộc allowlist hoặc có approval tương ứng.
- [ ] IAM, JIT support, MFA, break-glass, audit và field masking được cấu hình.
- [ ] TLS, encryption at rest, customer-managed key và key recovery được đánh giá.
- [ ] Provider/subprocessor có due diligence, DPA, location/support details và change notification.
- [ ] Control plane/global metadata không lộ dữ liệu vượt scope được phép.
- [ ] Retention, legal hold, deletion propagation và backup expiry có owner.
- [ ] Data export/portability và provider exit plan đã được xem xét.
- [ ] Policy-as-code có preventive guardrail, drift detection, corrective workflow và evidence.
- [ ] Exception có scope, compensating control, approver, expiry và periodic review.
- [ ] Có quy trình incident/legal request, evidence preservation và stakeholder communication.
- [ ] DR trong boundary đáp ứng RTO/RPO đã phê duyệt hoặc có risk acceptance.
- [ ] Có kiểm thử cross-border flow, denied region, support access, deletion và restore.
- [ ] ADR và data flow register có ngày review khi luật, provider hoặc purpose thay đổi.

**Ghi nhớ:** Chủ quyền dữ liệu không thể được chứng minh chỉ bằng vị trí database. Cần biết dữ liệu được lưu, xử lý, sao chép và truy cập từ đâu; ai có quyền, provider/subprocessor nào tham gia và mục đích nào được phép. Hãy lập data flow register, để legal/privacy xác nhận điều kiện transfer, rồi thực thi bằng regional placement, IAM, key control, backup policy, telemetry scrubbing và policy-as-code. Mọi ngoại lệ và bản sao phải có owner, thời hạn và bằng chứng kiểm toán.
