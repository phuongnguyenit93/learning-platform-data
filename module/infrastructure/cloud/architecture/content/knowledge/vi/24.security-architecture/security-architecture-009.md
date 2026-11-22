# Ghi nhật ký kiểm toán, phát hiện và ứng phó sự cố

Một hệ thống cloud có thể mã hóa dữ liệu, dùng least privilege và chạy nhiều lớp bảo vệ, nhưng vẫn khó điều tra khi không biết ai đã truy cập dữ liệu, policy nào đã thay đổi, request nào tạo ra hành động đáng ngờ hoặc sự cố bắt đầu từ đâu. Nếu log bị thiếu, timestamp không đồng nhất, dữ liệu bị sửa hoặc các thành phần ghi theo format khác nhau, đội vận hành có thể không dựng lại được diễn biến và không xác định được phạm vi ảnh hưởng.

**Ghi nhật ký kiểm toán (audit logging)** lưu lại các hành động có ý nghĩa về trách nhiệm và quản trị: ai thực hiện, hành động gì, trên tài nguyên nào, khi nào, từ ngữ cảnh nào và kết quả ra sao. **Security monitoring** phân tích telemetry để nhận diện hành vi bất thường hoặc dấu hiệu tấn công. **Incident response** là quy trình điều phối phát hiện, phân loại, khoanh vùng, loại bỏ nguyên nhân, phục hồi và rút kinh nghiệm sau sự cố.

Ba năng lực này liên quan nhưng phục vụ mục đích khác nhau. Audit log tạo bằng chứng về hành động; security telemetry cung cấp tín hiệu; detection logic kết hợp các tín hiệu để phát hiện; incident response biến cảnh báo thành hành động có kiểm soát.

Bài học này thuộc chương **Kiến trúc bảo mật** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế kiến trúc ghi nhận và bảo vệ sự kiện kiểm toán, tập trung log từ các thành phần cloud, xây dựng detection/use case, tổ chức ứng phó sự cố và quản lý bằng chứng. Các quyết định phải cân bằng khả năng truy vết, độ tin cậy, quyền riêng tư, chi phí, hiệu năng và vận hành theo tư duy Well-Architected.

## 1. Vì sao audit logging và incident response là năng lực kiến trúc?

Các câu hỏi thường xuất hiện sau sự cố:
- Ai đã đăng nhập hoặc sử dụng credential nào?
- Principal nào đọc, export, sửa hoặc xóa dữ liệu?
- Policy/IAM role nào đã thay đổi và ai phê duyệt?
- Một thay đổi production có đi qua pipeline được phê duyệt không?
- Tài khoản nào tạo access key, token hoặc workload identity?
- Request đáng ngờ đã ảnh hưởng tới tenant, object hoặc database nào?
- Sự cố bắt đầu khi nào, kéo dài bao lâu và đã được khoanh vùng ra sao?
- Có dữ liệu nào bị đọc, sửa, xóa hoặc đưa ra ngoài hệ thống không?

Nếu chỉ có application log dạng “request failed”, nhóm không thể trả lời phần lớn câu hỏi trên. Audit và security logging cần được thiết kế từ ranh giới identity, data access, control plane, network, application và deployment.

~~~mermaid
flowchart LR
    SRC["Identity / Cloud control plane / Network / Apps / Data"] --> COL["Collect and normalize"]
    COL --> PIPE["Secure log pipeline"]
    PIPE --> STORE[("Protected audit store")]
    PIPE --> SIEM["SIEM / analytics"]
    SIEM --> DET["Correlation and detection"]
    DET --> ALERT["Alert / case"]
    ALERT --> IR["Incident response"]
    IR --> FIX["Contain / eradicate / recover"]
    IR --> EVID["Evidence and lessons"]
~~~

Một kiến trúc tốt cần đạt:
- **Accountability:** xác định principal và hành động.
- **Traceability:** liên kết sự kiện giữa nhiều service.
- **Integrity:** phát hiện sửa/xóa trái phép và bảo vệ bằng chứng.
- **Availability:** log vẫn được ghi nhận khi một thành phần gặp lỗi.
- **Timeliness:** dữ liệu đến nơi phân tích đủ nhanh cho mục tiêu detection.
- **Privacy:** chỉ thu thập dữ liệu cần thiết, hạn chế PII/secret.
- **Actionability:** cảnh báo có owner, mức độ và quy trình xử lý.

## 2. Phân biệt các loại log và telemetry

Không phải mọi log đều là audit log. Gộp tất cả vào một nơi mà không phân loại sẽ làm khó quản lý retention, quyền truy cập và độ tin cậy.

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| **Audit log** | Ghi lại hành động có trách nhiệm/kiểm toán | IAM role thay đổi, admin export dữ liệu, object bị xóa |
| **Security event** | Sự kiện có ý nghĩa bảo mật | Login thất bại, MFA bị tắt, malware detection |
| **Application log** | Diễn giải hành vi ứng dụng và lỗi | Booking request validation failed |
| **Infrastructure/platform log** | Hoạt động runtime và nền tảng | Container restart, database failover |
| **Network telemetry** | Quan sát luồng và hành vi mạng | Flow logs, DNS queries, firewall deny |
| **Metrics** | Đo xu hướng/số lượng theo thời gian | Error rate, failed login count |
| **Trace** | Theo dấu request xuyên nhiều service | API gateway → booking → payment |
| **Business event** | Thay đổi trạng thái nghiệp vụ | BookingConfirmed, PaymentCaptured |

Một sự kiện có thể xuất hiện ở nhiều loại telemetry với góc nhìn khác nhau. Ví dụ thay đổi quyền database có thể có audit event từ control plane, application log của pipeline và alert từ SIEM. Cần có correlation ID hoặc change ID để liên kết mà không coi bản ghi trùng là một hành động độc lập.

### 2.1. Audit log khác application log

Application log có thể bị thay đổi cùng code, bị thiếu khi ứng dụng crash hoặc chỉ ghi điều mà developer dự kiến. Audit log cho hoạt động nhạy cảm nên được phát từ control plane, database audit facility hoặc thành phần quản trị độc lập khi có thể; ứng dụng vẫn có thể bổ sung business audit event cho các hành động domain-specific.

Ví dụ:
- Application log: “User updated booking”.
- Audit event hữu ích: principal, tenant, action, resource ID, timestamp, request/correlation ID, kết quả, actor type và context được phép ghi nhận.

Không được coi nội dung log do client gửi là bằng chứng danh tính đáng tin cậy. Actor phải được lấy từ identity đã xác thực ở server-side.

## 3. Xác định những sự kiện cần ghi

Không cần ghi mọi chi tiết ở cùng mức độ. Trước tiên lập inventory theo tài sản, threat model và yêu cầu tuân thủ.

### 3.1. Identity và access

- Đăng nhập thành công/thất bại, MFA enrollment/disable/reset.
- Token/key/certificate được cấp, thu hồi hoặc rotate.
- Role, group, policy, trust relationship thay đổi.
- Quyền admin/break-glass được kích hoạt.
- Service principal/workload identity được tạo hoặc đổi quyền.
- Truy cập bị từ chối tới tài nguyên nhạy cảm.
- Privileged session mở/đóng và hành động thực hiện.

### 3.2. Data access và data lifecycle

- Đọc/export dữ liệu có phân loại nhạy cảm.
- Tải xuống hoặc chia sẻ file/object.
- Tạo, sửa, xóa record quan trọng.
- Thay đổi encryption, key policy hoặc database audit config.
- Thay đổi backup, retention, replication và deletion policy.
- Truy cập bất thường theo volume, tenant, vị trí hoặc thời gian.
- Truy vấn hàng loạt hoặc hoạt động có dấu hiệu exfiltration.

### 3.3. Cloud control plane và infrastructure

- Tạo/xóa/sửa compute, database, network, storage và security group.
- Mở public endpoint hoặc thay đổi ingress/egress.
- Thay đổi route, firewall, WAF, DNS và load balancer.
- Tạo access key, snapshot, backup hoặc export.
- Tắt logging, monitoring, alert hoặc security service.
- Thay đổi cloud account/subscription/project, organization và billing access.

### 3.4. Application, deployment và workload

- Deploy/rollback production và thay đổi artifact.
- Thay đổi feature flag ảnh hưởng auth/data.
- Cập nhật secret reference hoặc environment config.
- Thao tác migration/schema.
- API administrative action và thao tác hỗ trợ khách hàng.
- Thay đổi chính sách fraud/risk hoặc ML model có ảnh hưởng quyết định.

| Sự kiện | Mức quan trọng tham khảo | Vì sao |
|---|---|---|
| Tắt audit logging | Rất cao | Có thể làm mất dấu các hành động tiếp theo |
| Thay đổi IAM admin policy | Rất cao | Có thể mở rộng quyền toàn hệ thống |
| Export hàng loạt PII | Rất cao | Nguy cơ rò rỉ dữ liệu |
| Tạo public bucket/endpoint | Cao | Có thể làm lộ tài nguyên |
| Deploy artifact production | Cao | Thay đổi code và hành vi hệ thống |
| Login thất bại đơn lẻ | Thấp–trung bình | Có thể là lỗi người dùng |
| Login thất bại tăng đột biến | Cao | Có thể là brute force hoặc credential stuffing |
| Read request thông thường | Tùy dữ liệu | Có thể cần audit ở dataset nhạy cảm |

Mức độ thực tế phụ thuộc criticality, threat model, dữ liệu và chính sách tổ chức. Không nên cảnh báo mức cao cho mọi login lỗi đơn lẻ vì sẽ tạo alert fatigue.

## 4. Thiết kế schema sự kiện kiểm toán

Một audit event nên có schema ổn định để tìm kiếm, tương quan và lưu trữ lâu dài.

Ví dụ JSON minh họa:

~~~json
{
  "eventId": "evt-01J8SECURITY",
  "eventTime": "2026-11-18T04:25:31.482Z",
  "eventType": "iam.policy.updated",
  "category": "identity",
  "severity": "high",
  "actor": {
    "type": "user",
    "principalId": "user-284",
    "sessionId": "sess-a82"
  },
  "source": {
    "service": "admin-api",
    "region": "region-a",
    "ip": "203.0.113.10"
  },
  "target": {
    "resourceType": "iam-policy",
    "resourceId": "booking-admin-policy"
  },
  "action": "update",
  "outcome": "success",
  "reason": "approved-access-change",
  "requestId": "req-783",
  "correlationId": "corr-91b",
  "changeId": "chg-2026-108",
  "schemaVersion": 1
}
~~~

Đây là ví dụ cấu trúc, không phải khuyến nghị đưa mọi trường vào mọi log. Địa chỉ IP có thể là dữ liệu cá nhân theo bối cảnh pháp lý; cần quy định mục đích, quyền và retention. Không ghi access token, password, private key, session cookie hoặc full payment data.

### 4.1. Các trường cốt lõi

| Trường | Mục đích | Yêu cầu |
|---|---|---|
| Event ID | Định danh sự kiện | Duy nhất, ổn định qua pipeline retry |
| Event time | Thời điểm hành động | UTC, có precision và source semantics |
| Ingestion time | Thời điểm collector nhận | Phát hiện delay và clock skew |
| Actor/principal | Ai thực hiện | Lấy từ identity đã xác thực |
| Action/event type | Hành động gì | Tên chuẩn hóa, versioned |
| Target/resource | Tác động lên đâu | Resource ID/namespace |
| Outcome | Thành công/thất bại | Giá trị có kiểm soát |
| Source/context | Service, region, session, request | Không đưa secret/PII thừa |
| Correlation/change ID | Liên kết workflow/change | Có mặt xuyên hệ thống khi phù hợp |
| Schema version | Diễn giải record | Hỗ trợ tiến hóa schema |

### 4.2. Thành công và thất bại đều quan trọng

Chỉ ghi hành động thành công sẽ bỏ lỡ nhiều dấu hiệu tấn công. Chỉ ghi thất bại lại thiếu lịch sử thay đổi thực tế. Với hành động nhạy cảm, cần ghi cả outcome, reason code và actor. Không lưu exception stack đầy đủ nếu nó chứa secret, query nhạy cảm hoặc payload người dùng.

### 4.3. Timestamp và clock skew

Log từ nhiều VM, container và region cần đồng bộ thời gian. Dùng nguồn time synchronization tin cậy, lưu timestamp UTC và phân biệt event time với ingestion time. Nếu hai máy lệch đồng hồ vài phút, phân tích thứ tự sự kiện có thể sai. Với workflow quan trọng, correlation ID và sequence/transaction reference hữu ích hơn việc chỉ dựa vào timestamp.

## 5. Phân biệt audit trail bất biến và log phân tích

Log analytics thường có thể được aggregate, transform hoặc expire nhanh để phục vụ dashboard. Bằng chứng kiểm toán cần mức bảo vệ cao hơn.

Các đặc tính nên xem xét:
- **Append-oriented:** ưu tiên thêm record thay vì sửa record cũ.
- **Access separation:** workload tạo log không có quyền sửa/xóa kho audit.
- **Tamper evidence:** phát hiện thay đổi trái phép qua hash, signature hoặc cơ chế integrity của dịch vụ.
- **Immutable retention:** dùng object lock/WORM hoặc retention lock cho loại bằng chứng cần bảo vệ.
- **Versioning:** giữ lịch sử object/log theo policy.
- **Independent account/project:** tách audit archive khỏi quyền quản trị workload.
- **Encryption:** bảo vệ dữ liệu và key theo phân loại.
- **Audit access to audit:** mọi truy cập, export, policy change và deletion attempt trên kho audit cũng được ghi nhận.

Không phải mọi log cần WORM. Áp dụng retention immutability quá rộng có thể lưu nhầm PII hoặc dữ liệu phải xóa, tăng chi phí và làm phức tạp legal hold. Xác định nhóm log nào là bằng chứng bắt buộc, thời hạn nào được phê duyệt và ai có quyền ngoại lệ.

### 5.1. Hash chain và tamper evidence

Một chuỗi hash có thể liên kết record hiện tại với record trước:

\[
H_i = Hash(H_{i-1} \parallel Record_i)
\]

Nếu record ở giữa bị thay đổi, hash tiếp theo không còn khớp. Tuy nhiên, hash chain đơn lẻ không bảo đảm chống kẻ tấn công có quyền sửa cả record lẫn toàn bộ chain. Cần bảo vệ checkpoint/signing key, lưu checkpoint ra trust boundary khác và giới hạn quyền thay đổi. Dịch vụ audit managed có thể cung cấp integrity validation riêng; cần hiểu chính xác cơ chế và phạm vi.

## 6. Kiến trúc thu thập và tập trung log

Một pipeline điển hình:

~~~mermaid
flowchart TB
    subgraph SOURCES["Nguồn sự kiện"]
        ID["Identity / IAM"]
        CP["Cloud control plane"]
        APP["Application audit"]
        DB["Database audit"]
        NET["Network / WAF / DNS"]
        CI["CI/CD and artifact"]
    end
    ID --> COL["Regional collectors / agents"]
    CP --> COL
    APP --> COL
    DB --> COL
    NET --> COL
    CI --> COL
    COL --> BUS[("Secure log transport / stream")]
    BUS --> NORM["Normalize / enrich / filter"]
    NORM --> HOT[("Hot searchable store / SIEM")]
    NORM --> ARCH[("Protected audit archive")]
    HOT --> DET["Detection rules / correlation"]
    DET --> CASE["Alert / incident case"]
~~~

Các lớp chính:
1. **Sources:** dịch vụ cloud, identity, network, database, application, CI/CD và security tooling.
2. **Collectors:** agent, native service integration hoặc regional collector.
3. **Transport/buffer:** stream, queue hoặc durable buffer để hấp thụ burst và collector outage.
4. **Normalization/enrichment:** chuẩn hóa schema, thêm context tài sản, identity, environment và severity.
5. **Storage:** hot store để tìm kiếm nhanh, archive để giữ lâu theo retention.
6. **Detection/analytics:** SIEM, rule engine, query và correlation.
7. **Case management:** alert, incident ticket, ownership và action tracking.

### 6.1. Độ tin cậy pipeline

Cần xem:
- Collector có buffer khi mạng hoặc central store lỗi không?
- Buffer có giới hạn dung lượng và encryption không?
- Pipeline có retry bounded, backpressure và dead-letter handling không?
- Event có event ID để loại duplicate khi at-least-once delivery không?
- Log có thể bị drop khi throughput vượt capacity không?
- Có alert khi source mất heartbeat hoặc ingestion volume giảm bất thường không?
- Central SIEM lỗi thì nguồn vẫn ghi log cục bộ hoặc archive được không?

Với audit event trọng yếu, cần xác định liệu ứng dụng phải từ chối hành động khi audit sink không khả dụng, hay ghi vào durable local/outbox buffer rồi gửi sau. Đây là quyết định nghiệp vụ: fail-closed giúp tránh hành động không audit được nhưng có thể làm gián đoạn hoạt động; fail-open duy trì dịch vụ nhưng tạo khoảng trống kiểm toán.

### 6.2. Audit logging không nên phụ thuộc hoàn toàn vào chính ứng dụng

Một ứng dụng bị chiếm quyền có thể sửa code để ngừng ghi log hoặc ghi thông tin giả. Vì vậy, các sự kiện quan trọng nên được thu từ nhiều trust boundary độc lập:
- Cloud control-plane audit do provider quản lý.
- IAM/identity provider sign-in và administrative audit.
- Database audit facility hoặc database activity stream.
- Network/WAF/firewall flow và deny events.
- Deployment platform và artifact provenance.
- Application business audit event cho domain action.

Tương quan nhiều nguồn giúp giảm phụ thuộc vào một logger đơn lẻ.

## 7. Lưu trữ, phân tầng và retention

Không cần tất cả dữ liệu được tìm kiếm với tốc độ như nhau hoặc giữ trong cùng thời gian.

| Tầng | Mục tiêu | Ví dụ |
|---|---|---|
| Hot/searchable | Điều tra và detection nhanh | Security event, audit mới, application security log |
| Warm | Tra cứu sự kiện cũ thường xuyên hơn | Audit theo tháng/quý |
| Cold/archive | Bảo tồn lâu dài, chi phí thấp | Compliance audit, incident evidence |
| Legal hold | Giữ không bị xóa theo yêu cầu hợp lệ | Hồ sơ điều tra hoặc tranh chấp |

Retention phải xuất phát từ nghĩa vụ pháp lý/tuân thủ và hợp đồng, mục đích xử lý dữ liệu, thời gian phát hiện/điều tra, data classification, data residency, chi phí lưu/truy vấn/restore và quy trình legal hold/deletion. Không có một retention period đúng cho mọi tổ chức. Cần phối hợp security, privacy, legal, records owner và business owner để phê duyệt chính sách. Dữ liệu nhạy cảm không nên giữ lâu “phòng khi cần” nếu mục đích và căn cứ không còn phù hợp.

### 7.1. Hot/warm/cold lifecycle

Một pipeline có thể lưu log mới ở hot SIEM trong khoảng phục vụ detection, sau đó archive vào object storage immutable. Cần xác minh archive có thể đọc trong incident, key giải mã tồn tại suốt retention, metadata/index đủ tìm file, integrity được kiểm tra, legal hold ngăn lifecycle deletion và evidence có thể export đúng phạm vi.

## 8. Quyền truy cập và separation of duties

Log có thể chứa thông tin về cấu trúc hệ thống, IP, hành vi quản trị, user identifier và sự kiện nhạy cảm. Quyền truy cập phải theo vai trò và mục đích.

Ví dụ phân quyền:
- **Workload logger:** chỉ append vào đúng stream/namespace.
- **Collector:** đọc nguồn được chỉ định, ghi vào transport; không sửa archive đã đóng.
- **Security analyst:** tìm kiếm dữ liệu theo quyền và phạm vi được phê duyệt.
- **Incident commander:** điều phối và yêu cầu evidence preservation.
- **Audit/compliance:** đọc record kiểm toán theo nhiệm vụ.
- **Archive administrator:** quản lý lifecycle nhưng không được tùy ý chỉnh nội dung bằng chứng.
- **Break-glass operator:** quyền khẩn cấp có thời hạn, approval và audit riêng.

Nguyên tắc:
- Tách quyền tạo log khỏi quyền xóa/sửa log.
- Tách người điều tra khỏi người có khả năng thay đổi bằng chứng khi cần.
- Ghi audit mọi thao tác đọc/export, policy change và deletion attempt.
- Dùng MFA/strong authentication cho privileged access.
- Không chia sẻ tài khoản analyst/admin.
- Kiểm tra định kỳ quyền và chứng minh principal bị điều tra không thể tự xóa dấu vết.

## 9. Phát hiện sự cố: từ sự kiện đơn lẻ tới chuỗi hành vi

Một security event đơn lẻ có thể vô hại hoặc chưa đủ kết luận. Detection thường cần context, baseline và correlation.

| Use case | Tín hiệu | Hướng phân tích |
|---|---|---|
| Brute force/credential stuffing | Nhiều login failure theo account/IP/device | Rate, phân bố mục tiêu và successful login sau chuỗi lỗi |
| Privilege escalation | Role/policy thay đổi bất thường | Actor, approval, resource và thời điểm |
| Account takeover | Login mới, MFA reset, token refresh bất thường | Identity context và hành động sau login |
| Data exfiltration | Download/export khối lượng lớn | User baseline, tenant, data class và network egress |
| Public exposure | Bucket/database/network mở public | Control-plane event và tài sản bị ảnh hưởng |
| Logging tampering | Audit source bị tắt hoặc retention giảm | Thay đổi security config và ingestion gap |
| Unusual workload identity | Service principal gọi API ngoài pattern | Principal, source, scope và workload revision |
| Suspicious deployment | Image/artifact lạ hoặc deploy ngoài change window | Digest, signer, pipeline identity và approval |
| Ransomware/destructive activity | Xóa hàng loạt, encryption/write burst, backup policy change | File/object/database activity, identity và timeline |

### 9.1. Correlation

Ví dụ chuỗi nghi vấn account takeover:
1. Nhiều login failure trên một account.
2. Login thành công từ thiết bị hoặc vị trí chưa thấy trước đó.
3. MFA reset hoặc thêm credential mới.
4. Principal lấy quyền cao hơn.
5. Truy cập/export một lượng lớn file.
6. Xóa audit/log hoặc thay retention policy.

Một rule chỉ nhìn login thành công sẽ bỏ lỡ chuỗi này. SIEM hoặc detection engine có thể kết hợp event theo principal, session, IP, device, resource, correlation ID và khoảng thời gian. Cần xử lý NAT/shared IP, proxy và travel pattern để tránh kết luận sai.

### 9.2. Baseline và anomaly detection

Baseline có thể theo số lần login/request theo user/service, khối lượng export/download theo tenant, thời gian/vị trí truy cập, API call theo workload identity, thay đổi cấu hình theo team/release và network egress/DNS query pattern.

Anomaly không đồng nghĩa attack. Một đợt release, batch job hoặc chiến dịch marketing có thể làm traffic tăng hợp lệ. Detection cần context về change calendar, owner, environment và approved maintenance.

## 10. Từ detection tới cảnh báo có thể hành động

Một alert hữu ích cần chứa:
- Detection/use-case ID và severity.
- Thời gian và event window.
- Principal, resource, account/tenant và region liên quan.
- Tóm tắt lý do rule kích hoạt.
- Các event/evidence link được bảo vệ.
- Asset criticality và data classification.
- Owner/team và escalation path.
- Hành động an toàn ban đầu đã được phê duyệt.
- False-positive feedback và trạng thái xử lý.

Không đưa full secret, token hoặc PII vào nội dung alert. Link evidence phải yêu cầu xác thực và authorization; không chia sẻ URL công khai.

### 10.1. Severity và prioritization

Có thể phân mức tham khảo:
- **Critical:** dấu hiệu compromise hoặc data exfiltration có bằng chứng mạnh, ảnh hưởng hệ thống/dữ liệu trọng yếu.
- **High:** privilege escalation, public exposure nghiêm trọng hoặc hoạt động destructive đáng ngờ.
- **Medium:** hành vi bất thường cần xác minh nhưng chưa thấy tác động trực tiếp.
- **Low/Informational:** sự kiện phục vụ baseline hoặc theo dõi.

Severity cần xét likelihood, impact, confidence, asset criticality, blast radius và khả năng containment. Không dùng confidence thấp nhưng impact cao làm lý do bỏ qua; có thể cần escalation để xác minh.

## 11. Incident response lifecycle

Một quy trình ứng phó có thể chia thành các giai đoạn:

~~~mermaid
flowchart LR
    PREP["Prepare"] --> DET["Detect / Analyze"]
    DET --> CON["Contain"]
    CON --> ERAD["Eradicate"]
    ERAD --> REC["Recover"]
    REC --> POST["Lessons learned"]
    POST --> PREP
~~~

### 11.1. Prepare — chuẩn bị

- Xác định incident commander, security lead, service owner, legal/privacy và communications owner.
- Duy trì contact/đường liên lạc ngoài hệ thống có thể bị ảnh hưởng.
- Chuẩn bị runbook cho account compromise, key leak, data exposure, ransomware, suspicious deploy và service outage.
- Kiểm tra quyền break-glass, tool forensic và evidence storage.
- Diễn tập tabletop và technical game day.
- Xác định tiêu chí escalation, severity và notification.

### 11.2. Detect and analyze — phát hiện và phân tích

- Xác nhận alert có phải incident không.
- Xác định asset, principal, tenant, region và loại dữ liệu liên quan.
- Dựng timeline từ audit, identity, network, application và control-plane log.
- Xác định initial access, persistence, privilege escalation và hành động đã thực hiện.
- Ước lượng blast radius, data exposure và thời gian ảnh hưởng.
- Bảo tồn bằng chứng trước khi thay đổi trạng thái hệ thống nếu điều kiện cho phép.

Tránh kết luận nguyên nhân quá sớm từ một alert. Ghi rõ dữ kiện đã xác minh, giả thuyết và điều chưa biết.

### 11.3. Contain — khoanh vùng

Mục tiêu là ngăn sự cố tiếp tục lan rộng trong khi giữ bằng chứng và duy trì chức năng thiết yếu nếu có thể.

Ví dụ:
- Disable hoặc hạn chế principal/session bị compromise.
- Revoke token/key/certificate theo quy trình.
- Block egress, isolate workload hoặc security group.
- Tạm dừng pipeline/deployment đáng ngờ.
- Chuyển endpoint sang maintenance hoặc read-only.
- Dừng export/batch job hoặc giới hạn download.
- Tách tài nguyên bị nhiễm khỏi network.

Containment có thể gây gián đoạn và làm mất trạng thái dễ bay hơi. Incident commander và owner cần chọn hành động theo tác động, urgency và yêu cầu bảo toàn evidence.

### 11.4. Eradicate — loại bỏ nguyên nhân

- Xóa persistence mechanism và credential bị lộ.
- Vá lỗ hổng và cấu hình sai.
- Rebuild workload từ image/artifact đã xác minh thay vì tin host bị compromise.
- Rotate secrets/key khi phù hợp, kiểm tra dependency dùng key cũ.
- Xóa backdoor/unauthorized account và sửa policy.
- Khắc phục root cause trong pipeline, identity hoặc network.
- Kiểm tra các region/account khác có cùng dấu hiệu.

Không chỉ xóa file hoặc process đáng ngờ mà bỏ qua initial access vector. Nếu không sửa nguyên nhân, attacker có thể quay lại.

### 11.5. Recover — phục hồi

- Khôi phục từ backup/artifact sạch.
- Xác minh integrity và data consistency.
- Đưa workload trở lại theo canary hoặc từng nhóm.
- Theo dõi persistence indicator, unusual access và error.
- Thu hồi quyền khẩn cấp sau khi không còn cần.
- Đối soát hoạt động nghiệp vụ và thông báo người bị ảnh hưởng theo nghĩa vụ phù hợp.

### 11.6. Lessons learned — rút kinh nghiệm

Ghi timeline/root cause đã xác minh; điều gì giúp phát hiện, điều gì làm chậm phản ứng; detection nào thiếu hoặc tạo false positive; phạm vi dữ liệu/người dùng bị ảnh hưởng; quyết định containment/recovery cần cải thiện; action item có owner, deadline và tiêu chí hoàn thành. Cập nhật runbook, threat model, architecture diagram và control. Review nên tập trung cải thiện hệ thống, không chỉ tìm người để quy lỗi.

## 12. Bảo toàn bằng chứng và chain of custody

Trong điều tra, log và artifact có thể cần được sử dụng làm bằng chứng nội bộ, audit hoặc theo yêu cầu pháp lý. Phải giữ nguồn gốc và lịch sử xử lý.

Các nguyên tắc:
- Ghi evidence ID, nguồn, thời gian thu thập và người thu thập.
- Lưu bản gốc trong vùng bảo vệ; phân tích trên bản copy khi phù hợp.
- Tạo checksum/hash và kiểm tra lại sau khi copy/export.
- Ghi mọi lần truy cập, chuyển giao, biến đổi và trích xuất.
- Đồng bộ timestamp và ghi nhận clock offset nếu biết.
- Giới hạn người được xem hoặc export evidence.
- Lưu công cụ/version và thao tác forensic có thể ảnh hưởng dữ liệu.
- Giữ metadata như provider request ID, object version, log sequence và source account.

**Chain of custody** là lịch sử có thể kiểm tra về việc thu thập, kiểm soát, chuyển giao và xử lý bằng chứng. Hash giúp kiểm tra integrity nhưng không tự chứng minh ai tạo record ban đầu hoặc nguồn log có đáng tin hay không. Cần kết hợp provenance, quyền truy cập, source-side audit và quy trình lưu giữ.

### 12.1. Preserve trước khi cleanup

Trong incident, quy trình cleanup tự động có thể xóa container, snapshot, log buffer hoặc object tạm. Cần đánh giá legal hold/evidence preservation trước khi chạy cleanup nếu điều kiện cho phép. Không trì hoãn containment cần thiết chỉ để thu thập mọi dữ liệu; ưu tiên theo mức độ nguy hiểm và khả năng mất bằng chứng.

## 13. Quyền riêng tư, dữ liệu nhạy cảm và retention

Audit log có thể trở thành một kho dữ liệu nhạy cảm mới. Logging quá mức có thể làm rò rỉ password, token, nội dung người dùng hoặc thông tin cá nhân.

Quy tắc:
- Không ghi password, private key, bearer token, session cookie hoặc secret.
- Tránh ghi full request/response body mặc định.
- Dùng identifier thay thế hoặc pseudonymization khi không cần danh tính trực tiếp.
- Mask hoặc redact trường PII và payment data.
- Giới hạn truy cập theo role, tenant, purpose và case.
- Xác định retention theo mục đích và nghĩa vụ.
- Có cơ chế legal hold và deletion/disposal khi hết hạn.
- Kiểm tra data residency và cross-region replication.
- Quản lý log export, analyst download và third-party SIEM processor.
- Thực hiện privacy review trước khi thêm telemetry mới.

Không phải cứ hash identifier là dữ liệu đã vô danh; giá trị có thể liên kết lại nếu có dữ liệu bổ trợ. Cần đánh giá khả năng re-identification theo bối cảnh.

## 14. Khác biệt giữa các dịch vụ cloud và công cụ tập trung

Các cloud provider và nền tảng thường có audit/control-plane service riêng, nhưng tên, phạm vi và khả năng thay đổi theo sản phẩm.

| Hệ sinh thái | Nguồn audit/control-plane thường gặp | Cần xác minh |
|---|---|---|
| **AWS** | CloudTrail management/data events, IAM events, VPC Flow Logs, service-specific audit logs | Event selector, data event cost, trail organization/account, integrity và destination |
| **Azure** | Azure Activity Log, resource diagnostic settings, Entra sign-in/audit logs, NSG flow logs và service logs | Subscription/tenant scope, diagnostic export, retention, category coverage và regional destination |
| **Google Cloud** | Cloud Audit Logs (Admin Activity, Data Access, System Event, Policy Denied), VPC Flow Logs, service audit | Data Access enablement/coverage, project/organization sinks, exclusion filters, destination và retention |

Một số log như data access có thể cần bật riêng hoặc có cost/volume cao. Không giả định mọi thao tác đọc dữ liệu đều được ghi mặc định. Cần lập coverage matrix theo resource/service và chạy test event để chứng minh log đã đến nơi.

### 14.1. SIEM và security data lake

SIEM thường tập trung tìm kiếm, correlation, rule, alert và case. Security data lake hoặc object archive phù hợp giữ lượng lớn telemetry lâu hơn và phân tích bằng query/batch. Có thể dùng cả hai:
- SIEM nhận sự kiện đã chuẩn hóa và cần detection nhanh.
- Archive lưu dữ liệu gốc/đã lọc theo retention.
- Query engine phân tích lịch sử hoặc threat hunting.
- Case management theo dõi incident và bằng chứng.

Cần kiểm tra connector, parsing, schema evolution, ingestion delay, duplicate handling và cost theo data volume.

## 15. Automation và SOAR: tự động hóa phản ứng có kiểm soát

Security orchestration, automation and response (SOAR) có thể tự động:
- Tạo incident case và enrich principal/IP/asset.
- Tra cứu threat intelligence theo policy.
- Lấy snapshot/log context và lưu evidence.
- Tạm thời giảm rate hoặc chặn một indicator đã được xác minh.
- Notify owner và tạo task.
- Revoke session hoặc disable key theo playbook được phê duyệt.
- Theo dõi remediation và đóng case sau xác nhận.

Không tự động disable account admin, xóa resource hoặc rotate một key dùng chung chỉ từ anomaly có confidence thấp. Automation có thể gây outage diện rộng hoặc phá hủy bằng chứng. Phân loại hành động:
- **Read-only enrichment:** thường có thể tự động.
- **Low-risk reversible action:** có thể tự động theo điều kiện rõ.
- **High-impact action:** cần approval hoặc confirmation.
- **Destructive action:** cần quy trình đặc biệt, preserve evidence và audit đầy đủ.

Mỗi playbook nên có version, owner, input validation, permission scope, timeout, rollback, idempotency và log kết quả.

## 16. Đo hiệu quả audit và incident response

Không chỉ đo số log được lưu hoặc số alert được tạo. Các chỉ số nên cho thấy hệ thống có phát hiện và ứng phó đúng lúc hay không.

| Metric | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Log source coverage | Tỷ lệ tài sản/sự kiện quan trọng có telemetry | Tìm blind spot |
| Ingestion delay | Thời gian từ event tới SIEM/store | Kiểm tra freshness detection |
| Event loss/drop rate | Số log bị mất hoặc loại bỏ | Đánh giá độ tin cậy pipeline |
| Parsing/schema failure | Sự kiện không chuẩn hóa được | Phát hiện thay đổi source/schema |
| Detection precision | Tỷ lệ alert có giá trị | Giảm false positive |
| Detection recall/use-case coverage | Tỷ lệ tình huống mô phỏng phát hiện được | Tìm detection gap |
| MTTD | Mean time to detect | Đánh giá tốc độ phát hiện |
| MTTA | Mean time to acknowledge | Đánh giá tốc độ tiếp nhận |
| MTTC | Mean time to contain | Đánh giá tốc độ khoanh vùng |
| MTTR | Mean time to recover/resolve theo định nghĩa tổ chức | Đánh giá phục hồi |
| Evidence completeness | Tỷ lệ incident có timeline/evidence cần thiết | Đánh giá khả năng điều tra |
| Runbook success rate | Tỷ lệ diễn tập/ứng phó hoàn thành đúng tiêu chí | Kiểm tra readiness |

Định nghĩa metric cần thống nhất. MTTR đôi khi được dùng cho restore hoặc resolve; hãy ghi rõ điểm bắt đầu/kết thúc và loại incident. Không dùng một số trung bình để che incident nghiêm trọng; phân tích theo severity và service tier.

## 17. Runbook mẫu: nghi ngờ export dữ liệu trái phép

~~~text
1. ALERT AND TRIAGE
   - Xác minh detection ID, principal, tenant, resource và event window.
   - Kiểm tra change window, ticket và hoạt động hợp lệ.
   - Xác định data classification và mức ảnh hưởng tiềm năng.

2. PRESERVE EVIDENCE
   - Lưu audit event gốc, identity/session event, network egress và application trace.
   - Ghi evidence ID, source, timestamp, collector và checksum.
   - Bật legal/evidence hold khi policy yêu cầu.

3. CONTAIN
   - Tạm dừng export hoặc giới hạn principal/session đáng ngờ.
   - Revoke session/token nếu có cơ sở.
   - Cô lập workload hoặc block egress khi cần và được phê duyệt.
   - Bảo đảm không gây gián đoạn quá mức cho tenant khác.

4. INVESTIGATE
   - Dựng timeline login -> privilege change -> data access -> export.
   - Xác định data/object/record, số lượng, tenant và destination.
   - Tìm persistence, credential reuse và dấu hiệu compromise khác.

5. ERADICATE AND RECOVER
   - Rotate credential/key theo phạm vi.
   - Loại quyền/automation trái phép và vá nguyên nhân.
   - Khôi phục service, kiểm tra integrity và theo dõi tái diễn.

6. NOTIFICATION AND CLOSE
   - Escalate tới legal/privacy/business owner theo policy.
   - Ghi impact, quyết định và evidence chain.
   - Cập nhật detection, runbook, control và action owner.
~~~

Runbook cần điều chỉnh theo loại dữ liệu và quyền hạn. Đội ứng phó không tự kết luận nghĩa vụ thông báo pháp lý chỉ từ log; chuyển cho legal/privacy owner đánh giá theo quy định áp dụng.

## 18. Đánh đổi theo Well-Architected

| Khía cạnh | Thiết kế tốt hỗ trợ | Rủi ro cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Log có buffer/archive, incident được phát hiện và phục hồi | Log loss, collector outage, alert không đến người trực | Pipeline failure test, source coverage, runbook drill |
| **Bảo mật** | Accountability, tamper evidence, least privilege, evidence protection | Log chứa secret/PII, admin xóa audit, SIEM quá rộng quyền | IAM review, integrity validation, redaction test |
| **Hiệu quả hiệu năng** | Detection kịp thời, truy vấn và correlation có mục tiêu | Logging synchronous quá nặng, ingestion/parse backlog | Ingestion latency, app overhead, query performance |
| **Tối ưu chi phí** | Tiering, filter theo use case, retention hợp lý | Log volume lớn, hot storage và SIEM ingestion đắt | Cost/GB, archive ratio, retention review |
| **Vận hành xuất sắc** | Runbook, ownership, case workflow và lessons learned | Alert fatigue, không có on-call, playbook gây side effect | MTTD/MTTC, game day, detection quality |
| **Bền vững** | Giữ dữ liệu có mục đích, lifecycle và dung lượng phù hợp | Lưu telemetry thừa, replicate vô ích, query compute kéo dài | Data minimization, lifecycle metrics, storage inventory |

Các đánh đổi quan trọng:
- Thu thập nhiều hơn tăng khả năng điều tra nhưng tăng cost, privacy exposure và noise.
- Audit synchronous trước hành động có thể bảo đảm không bỏ event nhưng tăng latency và availability dependency.
- Centralized SIEM giúp correlation nhưng tạo tập trung dữ liệu và một dependency vận hành.
- Immutable archive tăng integrity nhưng giảm khả năng sửa/xóa; retention phải được phê duyệt kỹ.
- Tự động containment giảm thời gian phản ứng nhưng có nguy cơ khóa nhầm người dùng hoặc gây outage.
- Multi-region log replication tăng khả năng sống sót nhưng cần kiểm soát data residency, key và egress.

## 19. Quy trình thiết kế audit và incident response

Một architecture review có thể tiến hành theo thứ tự:

1. **Xác định tài sản và threat model:** dữ liệu nào quan trọng, attacker có thể làm gì và hành động nào phải truy vết?
2. **Lập event inventory:** identity, control plane, data access, network, application, deployment và third-party.
3. **Xác định schema:** actor, action, target, event time, outcome, correlation ID và version.
4. **Chọn trust boundary:** nguồn nào độc lập với workload, nguồn nào có thể bị attacker sửa?
5. **Thiết kế pipeline:** collector, buffer, normalize, SIEM, archive và failure handling.
6. **Phân loại integrity:** log nào cần append-only, tamper evidence, immutable retention hoặc legal hold?
7. **Định nghĩa access policy:** ai ghi, đọc, export, xóa và thay đổi retention?
8. **Thiết kế privacy/retention:** data minimization, redaction, residency và lifecycle.
9. **Xây dựng detection use case:** tín hiệu, correlation, baseline, confidence và severity.
10. **Gắn alert với owner/runbook:** escalation, on-call, evidence và approval.
11. **Thiết kế incident lifecycle:** prepare, detect/analyze, contain, eradicate, recover và lessons learned.
12. **Định nghĩa metrics:** source coverage, ingestion delay, MTTD/MTTC, evidence completeness và cost.
13. **Kiểm thử:** giả lập log source mất, log bị sửa, credential compromise, export bất thường và SIEM outage.
14. **Rà soát định kỳ:** quyền, rule, retention, false positive, drift và coverage theo thay đổi kiến trúc.

### Checklist review ngắn

| Hạng mục | PASS khi |
|---|---|
| Audit coverage | Sự kiện privileged, data access và control-plane quan trọng được liệt kê |
| Identity context | Actor lấy từ danh tính xác thực, không tin client-supplied value |
| Schema/time | Event ID, UTC time, outcome, correlation và schema version rõ |
| Integrity | Có trust boundary, access separation và tamper detection phù hợp |
| Pipeline resilience | Buffer, retry, loss alert và archive hoạt động khi SIEM lỗi |
| Privacy | Secret/PII được loại bỏ hoặc giới hạn có chủ đích |
| Retention | Có owner, mục đích, thời hạn, legal hold và deletion process |
| Detection | Use case có logic, test data, severity và owner |
| Incident response | Có commander, runbook, on-call và escalation |
| Evidence | Chain of custody và access audit được lưu |
| Recovery | Containment/recovery có tiêu chí và rollback |
| Cost | Log volume, SIEM ingestion và archive cost được đo |

## 20. ADR minh họa — Ghi audit cho thao tác export hồ sơ Booking

> **Bối cảnh:** Admin có thể export hồ sơ khách hàng phục vụ hỗ trợ. Hệ thống cần truy vết principal, tenant, phạm vi export và kết quả; đồng thời tránh ghi nội dung hồ sơ vào log.
>
> **Phương án A:** Chỉ ghi application log trong Admin API. Dễ triển khai nhưng ứng dụng có thể ngừng ghi, format thay đổi và operator có quyền trên app có thể ảnh hưởng log.
>
> **Phương án B:** Admin API phát business audit event có schema chuẩn, identity lấy từ server-side session; cloud identity/control-plane audit và data access log cung cấp nguồn độc lập. Event được gửi qua durable buffer tới SIEM và archive tách quyền.
>
> **Quyết định minh họa:** Chọn B. Ghi actor, tenant, export job ID, data category, record count, destination type, approval/change ID và outcome; không ghi payload, token hoặc email đầy đủ.
>
> **Integrity:** Workload chỉ append; archive tách account/role, có retention policy và access audit. Detection cảnh báo export vượt baseline hoặc ngoài change window.
>
> **Response:** Alert tạo case, analyst xác minh ticket/approval, preserve evidence và containment theo runbook.
>
> **Kiểm chứng:** Giả lập export hợp lệ/bất thường, collector outage, SIEM outage, thiếu field, access chéo tenant, log tampering attempt và kiểm tra retention.
>
> **Điều kiện xem xét lại:** Thay đổi nghĩa vụ kiểm toán, loại dữ liệu, lượng log hoặc khả năng source audit của nền tảng.

## 21. Bài tập thực hành: phát hiện và ứng phó export bất thường

Một nền tảng đặt chỗ có Admin API, relational database, object storage và nhiều workload identity. Một tài khoản hỗ trợ đăng nhập lúc 02:15 UTC, sau đó role được nâng lên quyền export. Trong 12 phút, tài khoản tạo 4 export job, tải về lượng lớn hồ sơ khách hàng và thay đổi retention của một log bucket. SIEM chỉ nhận application log; cloud control-plane audit và object data access chưa được bật đầy đủ. Central SIEM đặt trong cùng region với ứng dụng.

**Yêu cầu:**
1. Xác định các nguồn log còn thiếu và trust boundary cần bổ sung.
2. Thiết kế audit event schema cho login, role change, export job và retention update.
3. Xây dựng correlation rule cho chuỗi hành động theo principal/session.
4. Xác định cách phân biệt hoạt động hỗ trợ hợp lệ với account takeover.
5. Đề xuất containment theo mức độ và tránh phá hủy evidence.
6. Thiết kế archive độc lập với region ứng dụng và SIEM.
7. Xác định cách bảo vệ log, retention, encryption và access policy.
8. Viết runbook dựng timeline và xác định phạm vi dữ liệu bị tải.
9. Chọn metric về coverage, ingestion delay, MTTD/MTTC và evidence completeness.
10. Đề xuất game day cho trường hợp attacker tắt audit source hoặc central SIEM không khả dụng.

### Hướng giải quyết

- Bật và kiểm thử identity/sign-in audit, cloud control-plane events, database audit phù hợp, object data access, network egress và deployment/config change.
- Actor phải lấy từ identity provider/server-side principal. Gắn session ID, correlation ID, export job ID và change/approval ID.
- Correlate login bất thường → privilege escalation → nhiều export → object read/download tăng → retention change; severity dựa trên data classification, confidence và asset impact.
- Kiểm tra ticket, lịch trực, MFA/device context, approval và hành vi lịch sử; không coi IP mới đơn lẻ là bằng chứng compromise.
- Preserve log gốc, snapshot/config history và evidence metadata; sau đó revoke session/credential, dừng export và isolate principal theo approval/runbook.
- Đưa archive sang account/region độc lập, append-only/immutable theo policy, encryption và access audit; có local buffer khi SIEM unavailable.
- Không ghi nội dung hồ sơ, token hoặc PII đầy đủ vào alert. Ghi record/object reference và số lượng.
- Dựng timeline từ identity, IAM, application, database, object và network logs; đối soát object/record đã truy cập, destination và kết quả export.
- Theo dõi nguồn log coverage, ingestion delay, event drop, detection precision, MTTD/MTTC và evidence completeness.
- Diễn tập tắt logging, mất collector/SIEM, quyền analyst bị compromise và archive restore; xác minh alert đường ngoài region hoạt động.

### Câu hỏi tự kiểm tra

1. Audit log khác application log và security event như thế nào?
2. Vì sao cần ghi cả hành động thành công và thất bại?
3. Làm sao xác định actor đáng tin cậy khi client tự gửi user ID?
4. Vì sao nên thu thập audit từ nhiều trust boundary?
5. Append-only và immutable retention khác gì log analytics thông thường?
6. Hash chain có thể phát hiện thay đổi nhưng không tự giải quyết rủi ro nào?
7. Khi nào ứng dụng nên fail-closed nếu audit sink không khả dụng?
8. Vì sao central SIEM trong cùng region có thể làm mất khả năng quan sát khi region lỗi?
9. Detection correlation khác cảnh báo từ một event đơn lẻ ra sao?
10. Các giai đoạn incident response gồm những bước nào và mục tiêu của containment là gì?
11. Chain of custody cần ghi lại những gì?
12. Làm sao cân bằng retention, privacy, legal hold và chi phí?

Một kiến trúc bảo mật trưởng thành không chỉ phát hiện một cảnh báo. Nó phải **ghi lại hành động có trách nhiệm từ nguồn đáng tin, bảo vệ tính toàn vẹn và quyền truy cập của bằng chứng, liên kết tín hiệu thành detection có thể hành động và đưa incident qua quy trình ứng phó được diễn tập**. Khi audit, monitoring và incident response được thiết kế xuyên suốt identity, control plane, data và application, tổ chức có thể hiểu điều gì đã xảy ra, giới hạn tác động và cải thiện khả năng chống chịu sau mỗi sự cố.
