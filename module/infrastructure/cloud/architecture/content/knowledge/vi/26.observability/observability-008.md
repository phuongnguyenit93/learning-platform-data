# Che dữ liệu nhạy cảm trong log và phân quyền truy cập

Log, trace và telemetry giúp đội ngũ vận hành hiểu điều gì đang xảy ra trong hệ thống cloud. Chúng ghi lại request, lỗi, độ trễ, trạng thái dependency và hành động quản trị để hỗ trợ debug, cảnh báo và điều tra sự cố. Nhưng các bản ghi này cũng có thể chứa email, số điện thoại, địa chỉ, session ID, access token, thông tin thanh toán, nội dung request hoặc dữ liệu định danh khác. Một hệ thống quan sát được thiết kế thiếu kiểm soát có thể trở thành nơi tập trung dữ liệu nhạy cảm, mở rộng phạm vi rò rỉ và làm tăng rủi ro tuân thủ.

**Che dữ liệu nhạy cảm trong log** là việc giảm thiểu, loại bỏ, mask, redact, tokenize hoặc biến đổi dữ liệu trước khi ghi hay chia sẻ telemetry. **Phân quyền truy cập** là việc giới hạn ai được xem, tìm kiếm, tải xuống, sửa đổi, cấu hình hoặc quản trị dữ liệu quan sát theo vai trò, mục đích và phạm vi cần thiết. Hai kiểm soát phải đi cùng nhau: che dữ liệu giảm mức độ nhạy cảm của bản ghi; phân quyền giảm khả năng một người hoặc workload truy cập phần dữ liệu còn lại.

Không nên xem log là dữ liệu phụ hoặc mặc định rằng chỉ kỹ sư mới xem được. Log có thể được chuyển qua agent, broker, observability SaaS, archive, SIEM, ticket, export và backup. Mỗi bản sao cần nằm trong data inventory, có classification, owner, retention và access policy. Kiến trúc cũng cần bằng chứng rằng quy tắc che dữ liệu vẫn hoạt động sau khi ứng dụng, schema hoặc pipeline thay đổi.

Bài học thuộc phần **Khả năng quan sát** trong học phần thiết kế kiến trúc cloud. Trọng tâm là bảo vệ dữ liệu nhạy cảm trong telemetry trong khi vẫn duy trì khả năng debug, phát hiện sự cố và điều tra, cân bằng bảo mật, độ tin cậy, hiệu năng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Nhận diện dữ liệu nhạy cảm trong log, trace, metric, event và audit record.
- Thiết kế data minimization, structured logging, redaction, masking và tokenization.
- Phân quyền truy cập observability theo role, attribute, environment và data scope.
- Tách quyền xem dữ liệu, truy vấn, export, quản trị pipeline và thay đổi retention.
- Bảo vệ log/audit trail, secret, backup và luồng chuyển dữ liệu telemetry.
- Kiểm thử chống rò rỉ qua exception, header, query parameter, trace baggage và payload.
- Xây dựng retention, deletion, break-glass, audit và continuous monitoring cho hệ thống quan sát.

## 1. Vì sao log và telemetry cần được bảo vệ?

Một request có thể đi qua API gateway, ứng dụng, database, message broker và dịch vụ bên ngoài. Để điều tra lỗi, hệ thống thường ghi request metadata, user/tenant context, error detail, SQL information, trace span và correlation ID. Nếu log toàn bộ request/response để tiện debug, những trường vốn chỉ xuất hiện ở đường nghiệp vụ có thể bị sao chép sang nhiều hệ thống quan sát.

Một bản ghi có thể vô tình chứa:

- Authorization header hoặc cookie session.
- Email, số điện thoại, tên và địa chỉ người dùng.
- Access token, refresh token, API key hoặc password.
- Số thẻ, bank reference hoặc dữ liệu thanh toán.
- Nội dung hồ sơ, ghi chú tự do hoặc payload chứa dữ liệu nhạy cảm.
- SQL bind parameter, exception message hoặc URL có thông tin định danh.

Một bản ghi có thể ít nhạy cảm riêng lẻ nhưng trở nên nhạy cảm khi liên kết với user ID, IP, timestamp và lịch sử hoạt động. Vì vậy cần đánh giá cả khả năng liên kết, mục đích sử dụng và phạm vi người có thể truy cập.

| Rủi ro | Hậu quả |
| --- | --- |
| Secret/token bị ghi vào log | Người xem log có thể truy cập hệ thống hoặc phiên người dùng |
| PII bị thu thập quá mức | Phạm vi xử lý và rò rỉ dữ liệu tăng |
| Quyền observability quá rộng | Người không cần dữ liệu nhạy cảm vẫn có thể tìm kiếm/export |
| Log được gửi ra sai region/vendor | Vi phạm residency, hợp đồng hoặc policy |
| Retention quá dài | Tăng thời gian phơi lộ và chi phí |
| Log bị sửa/xóa | Mất bằng chứng điều tra và khả năng audit |
| Debug trace chứa payload | Dữ liệu nhạy cảm lan sang nhiều span, dashboard và ticket |

## 2. Xác định phạm vi và phân loại telemetry

Kiểm soát bắt đầu từ inventory, không bắt đầu ở nút cấu hình mask trong log platform. Hãy xác định mọi nguồn tạo telemetry và mọi đích nhận dữ liệu.

| Loại | Nội dung thường gặp | Rủi ro |
| --- | --- | --- |
| Application log | Message, exception, request context, business state | PII/secret trong message hoặc stack context |
| Access log | IP, path, query, user agent, identity | Identifier và query parameter nhạy cảm |
| Distributed trace | Span name, attributes, baggage, URL, downstream metadata | Payload/PII được truyền qua nhiều service |
| Metric | Label, dimension, tag, value | Identifier trong label, cardinality cao |
| Audit log | Actor, action, resource, outcome, approval | Lộ hoạt động nhạy cảm; cần bảo vệ integrity |
| Security event | Login, denied access, privilege change, alert | Thông tin xác thực, account và điều tra |
| Pipeline/agent log | Parser error, dropped event, retry payload | Nội dung gốc xuất hiện trong error message |
| Query/DB log | SQL, bind values, query plan, user/database | Customer data hoặc credential trong parameter |

### Phân lớp dữ liệu trong telemetry

| Lớp minh họa | Ví dụ | Cách xử lý gợi ý |
| --- | --- | --- |
| Public/operational | Service name, version, status code | Ghi theo nhu cầu vận hành |
| Internal | Request ID, deployment ID, dependency name | Truy cập nhân viên có nhu cầu công việc |
| Confidential | User ID, tenant ID, IP, business reference | Mask/pseudonymize khi không cần giá trị thật; role hạn chế |
| Restricted | Token, password, payment credential, nội dung hồ sơ nhạy cảm | Không ghi; loại bỏ trước ingestion và kiểm thử không xuất hiện |

Tên lớp phải theo policy của tổ chức. IP hoặc user ID có thể là dữ liệu cá nhân trong một số bối cảnh. Không chỉ dựa vào field name; cần phân tích nội dung, khả năng liên kết và mục đích.

### Data flow map

~~~mermaid
flowchart LR
    APP["Application / Gateway"] --> AGENT["Collector / Agent"]
    DB["Database / Broker"] --> AGENT
    AGENT --> FILTER["Filter / Redaction / Enrichment"]
    FILTER --> PIPE["Telemetry pipeline"]
    PIPE --> OBS["Observability platform"]
    PIPE --> SIEM["Security analytics"]
    OBS --> ARCHIVE["Archive / Backup"]
    OBS --> DASH["Dashboard / Search / Alert"]
    SIEM --> CASE["Incident case / Evidence"]
~~~

Ở mỗi cạnh, ghi rõ protocol, identity, encryption, region, data class, retry behavior và quyền truy cập. Đừng quên telemetry từ staging, CI/CD, support tooling và thiết bị quản trị.

## 3. Nguyên tắc data minimization và structured logging

Cách hiệu quả nhất để bảo vệ dữ liệu là không thu thập dữ liệu không cần thiết. Masking ở cuối pipeline không thể xóa hoàn toàn rủi ro nếu bản ghi gốc đã đi qua nhiều queue hoặc lưu vào buffer.

Ưu tiên schema log có allowlist các field được phép thay vì ghi toàn bộ request object rồi cố gắng xóa field cấm. Ví dụ:

~~~json
{
  "timestamp": "2026-11-18T04:30:00Z",
  "level": "INFO",
  "service": "booking-api",
  "environment": "production",
  "event": "booking.confirmation",
  "request_id": "req-a813",
  "tenant_ref": "tenant-hash-32",
  "booking_ref": "bk-9281",
  "outcome": "success",
  "duration_ms": 84
}
~~~

Record chỉ chứa thông tin cần để hiểu sự kiện. Không đưa tên, email, số điện thoại hoặc token vào nếu query vận hành không cần chúng.

Structured logging giúp parser và policy xử lý field chính xác hơn so với chuỗi tự do. Cần schema/version rõ, field name thống nhất, timestamp chuẩn, correlation ID, enum/operation name, giới hạn kích thước và nesting. Tuy vậy, structured logging không tự bảo đảm an toàn: trường payload dạng JSON tự do vẫn có thể chứa secret hoặc PII.

Exception message có thể bao gồm URL, SQL, query parameter, request body hoặc response từ provider. Hãy log exception class, error code, operation name và stack trace đã được review; không mặc định nối toàn bộ input/output vào message. Nếu cần payload để điều tra, dùng capture có kiểm soát, thời hạn ngắn, approval và audit.

## 4. Kỹ thuật redact, mask, tokenize và pseudonymize

Các kỹ thuật này không tương đương nhau. Chọn theo mục đích, khả năng khôi phục và nhu cầu liên kết bản ghi.

| Kỹ thuật | Cách làm | Có khôi phục được không? | Ví dụ |
| --- | --- | --- | --- |
| **Redaction** | Loại bỏ giá trị hoặc thay bằng placeholder | Không từ bản log đã redact | Xóa Authorization header |
| **Masking** | Che một phần giá trị | Có thể suy đoán phần bị che nếu miền giá trị nhỏ | Hiển thị ***1234 |
| **Tokenization** | Thay bằng token tham chiếu; mapping lưu riêng | Có, qua token vault và quyền phù hợp | Thay account number bằng token |
| **Pseudonymization** | Thay identifier bằng mã giả có thể liên kết có kiểm soát | Có thể liên kết nếu có key/mapping | HMAC user ID bằng secret riêng |
| **Hashing** | Biến đổi một chiều | Giá trị dễ đoán có thể bị dò | Fingerprint identifier có entropy đủ |
| **Aggregation** | Gộp thành nhóm hoặc thống kê | Không giữ từng record nếu thiết kế đúng | Số lỗi theo service/region |

Redaction phù hợp cho secret và dữ liệu không cần trong telemetry. Xóa toàn bộ field nhạy cảm thay vì chỉ che một phần. Authorization, Cookie, Set-Cookie, password, client_secret, private_key và refresh_token cần bị loại bỏ.

Masking hữu ích khi người vận hành cần một phần nhận diện, ví dụ vài ký tự cuối của reference. Nhưng masking không phải ẩn danh hoàn toàn. Với email hoặc số điện thoại, phần còn lại có thể đủ để nhận dạng trong tập dữ liệu nhỏ.

Tokenization và pseudonymization giúp liên kết sự kiện của cùng đối tượng mà không đưa identifier gốc vào log. Cần kiểm soát key/mapping, scope và rotation. HMAC có secret thường phù hợp hơn hash thường cho identifier có miền giá trị nhỏ; không dùng secret chung toàn tổ chức nếu cần giới hạn khả năng liên kết giữa hệ thống.

Không dùng mã hóa tự chế, base64 hoặc hash không salt như biện pháp bảo vệ PII. Base64 chỉ là encoding. Chọn primitive và key management đã được đánh giá; xác định rõ mục tiêu là redaction, pseudonymization hay encryption có thể giải mã.

## 5. Che dữ liệu ở đâu trong pipeline?

Nguyên tắc là che càng sớm càng tốt, trước khi dữ liệu nhạy cảm được gửi tới hệ thống có phạm vi truy cập rộng.

~~~mermaid
flowchart TD
    SRC["Application emits structured event"] --> APP["Allowlist + safe logger"]
    APP --> AGENT["Agent / SDK filters"]
    AGENT --> PROC["Collector redaction processor"]
    PROC --> VALID{"Schema and policy pass?"}
    VALID -- "Yes" --> STORE["Approved telemetry store"]
    VALID -- "No" --> QUAR["Quarantine / reject with safe reason"]
    STORE --> VIEW["Role-scoped views"]
    VIEW --> USER["Authorized operator"]
    STORE --> AUDIT["Access audit"]
~~~

Các lớp kiểm soát:

1. Application layer: không log field nhạy cảm; dùng schema allowlist và helper an toàn.
2. SDK/agent: filter header, attribute và field được biết trước khi gửi.
3. Collector/processor: redaction theo schema, policy version và destination.
4. Ingestion gateway: kiểm tra dữ liệu đầu vào, reject hoặc quarantine record vi phạm.
5. Storage/query layer: field-level policy, masking view và hạn chế quyền raw data.
6. Export/share layer: kiểm tra permission và áp dụng redaction trước khi tải hoặc đính kèm ticket.

Không dựa vào duy nhất một regex ở collector. Field mới, nested payload hoặc service bypass collector có thể tạo đường rò rỉ. Kết hợp schema allowlist, code review, automated tests, collector processor, DLP scanner và restricted access với raw data.

Nếu processor phát hiện secret hoặc PII không được phép, drop/redact theo policy; ghi metric/alert không chứa giá trị nhạy cảm; chỉ quarantine khi có nhu cầu điều tra và nơi quarantine được bảo vệ tương ứng. Không copy nguyên payload vi phạm vào error log. Cần quy trình purge bản ghi đã lọt vào destination và đánh giá incident.

## 6. Trace, span, baggage và metric label

Distributed tracing có nguy cơ lan truyền dữ liệu nhạy cảm vì span và baggage đi qua nhiều service.

- Span chỉ nên ghi operation name, service, status, duration và identifier được phê duyệt; tránh request/response body, authorization header, raw user email hoặc payment reference nhạy cảm.
- Baggage có thể được truyền tự động qua service. Không đặt token, PII hoặc secret vào baggage nếu chưa kiểm soát propagation và destination.
- URL có thể chứa email, reset token, search query hoặc identifier. Chuẩn hóa route template và loại bỏ query parameter nhạy cảm.
- Không đưa raw user ID, email, request ID hoặc token vào metric label. Dùng nhóm chuẩn hóa như service, route template, status class hoặc region.

Ví dụ route log nên dùng /users/{userId}/bookings cùng pseudonymous reference thay vì URL đầy đủ chứa email hoặc token.

## 7. Phân quyền truy cập observability

Một nền tảng observability thường có nhiều loại người dùng: developer, SRE, security analyst, support, data analyst, auditor và vendor. Họ không cần cùng một quyền.

### Tách quyền theo hành động

- Xem dashboard tổng hợp.
- Search log ở phạm vi service/environment.
- Xem field nhạy cảm hoặc raw event.
- Truy vấn trace và liên kết identity.
- Tạo/sửa alert và dashboard.
- Thay đổi collector/filter/pipeline.
- Export/download/share dữ liệu.
- Thay đổi retention, archive và deletion.
- Quản trị user/role, API key và integration.

Quyền xem log không nên mặc nhiên bao gồm quyền export toàn bộ log. Quyền sửa dashboard không nên bao gồm quyền tắt audit hoặc thay đổi retention.

### RBAC

| Role | Quyền gợi ý | Giới hạn |
| --- | --- | --- |
| Developer | Dashboard và log của service được giao | Không xem raw PII/secret, không export toàn hệ thống |
| SRE | Metrics, trace, log vận hành và incident scope | Production access được audit, raw data hạn chế |
| Security analyst | Security event, audit và điều tra theo case | Không mặc nhiên xem mọi business payload |
| Support | Trạng thái và thông tin tối thiểu của case | Mask identifier, chỉ tenant/customer được phân công |
| Auditor | Evidence/read-only trong scope và kỳ audit | Không sửa/xóa log hoặc cấu hình |
| Observability admin | Quản trị platform, pipeline và user | Privileged access có thời hạn, audit riêng |

RBAC dễ quản lý nhưng có thể quá rộng nếu role không phản ánh environment, service và tenant.

### ABAC và scope-based access

Attribute-based access control sử dụng thuộc tính như identity, team, service owner, environment, region, tenant, data classification, ticket ID và thời hạn truy cập.

~~~text
allow search_logs if
  user.team == log.service_owner_team
  and log.environment in user.approved_environments
  and log.classification <= user.clearance
  and log.region in user.allowed_regions

allow raw_event_view if
  user.role == security_investigator
  and request.ticket_id is approved
  and access.session_is_time_limited
~~~

Đây là pseudocode mô tả quyết định, không phải cú pháp của một sản phẩm cụ thể. Cần kiểm tra policy thực tế ở UI, API, query endpoint và export route.

### Tenant isolation

Nếu observability platform chứa dữ liệu nhiều tenant, tenant boundary cần áp dụng server-side. Không dựa vào dashboard filter mà người dùng có thể bỏ. Kiểm soát bao gồm dataset/index/stream scope, query API, saved search, alert destination, export, scheduled report, share link và support access.

## 8. Privileged access, break-glass và vendor access

Một số điều tra cần quyền rộng hơn bình thường. Quyền đặc biệt cần quy trình rõ, không cấp thường trực chỉ để tiện.

### Just-in-time access

- Người yêu cầu nêu mục đích, phạm vi, thời hạn và incident/ticket.
- Owner hoặc approver phù hợp phê duyệt.
- Hệ thống cấp role/permission tạm thời.
- Session được audit, giới hạn export và ghi nhận truy vấn nhạy cảm.
- Quyền tự hết hạn; extension cần lý do và approval mới.
- Sau phiên, review hành động nếu phạm vi có rủi ro cao.

### Break-glass và vendor access

Break-glass dùng khi quy trình bình thường không đủ xử lý sự cố khẩn cấp. Credential phải được bảo vệ, MFA/approval theo policy, cảnh báo ngay khi sử dụng và review sau sự kiện. Không ghi credential break-glass vào log hoặc runbook công khai.

Vendor chỉ nên truy cập dataset/service cụ thể, trong thời gian được phép và theo hợp đồng. Ưu tiên session do tổ chức khởi tạo/giám sát, mask dữ liệu trước khi chia sẻ và lưu audit. Xác minh support portal hoặc telemetry SaaS có data processing terms, subprocessor và residency phù hợp.

## 9. Audit truy cập và bảo vệ log

Operational log hỗ trợ debug; audit log ghi nhận ai đã thực hiện hành động quan trọng và phải được bảo vệ khỏi sửa/xóa trái phép.

Những hành động cần audit:

- Login, failed login và thay đổi MFA/session.
- Search/query vào dữ liệu nhạy cảm.
- Xem raw event hoặc mở restricted field.
- Export/download/share và tạo saved report.
- Thay đổi role, group, policy và API key.
- Thay đổi redaction processor, retention, routing và destination.
- Xóa log, archive hoặc backup.
- Break-glass, vendor access và quyền nâng cao.

Một audit record có thể ghi:

~~~json
{
  "event": "observability.data_export",
  "actor": "user-opaque-81",
  "actor_role": "security_investigator",
  "scope": "service:booking-api",
  "classification": "confidential",
  "ticket_ref": "INC-2041",
  "outcome": "approved",
  "timestamp": "2026-11-18T04:45:00Z",
  "correlation_id": "audit-9c11"
}
~~~

Không ghi truy vấn có payload nhạy cảm hoặc token vào audit event. Ghi metadata cần thiết để trả lời ai, làm gì, trên phạm vi nào, khi nào, theo phê duyệt nào và kết quả ra sao.

Để bảo vệ integrity, gửi audit record đến storage có quyền riêng biệt; hạn chế quyền sửa/xóa; dùng immutable/WORM option nếu phù hợp; đồng bộ thời gian; giám sát mất log; mã hóa và backup; kiểm thử rằng thao tác nhạy cảm tạo event.

## 10. Retention, archive và deletion

Không nên giữ log mãi mãi. Thời hạn cần dựa trên mục đích vận hành, điều tra, hợp đồng, quy định và chi phí.

| Dataset | Retention policy cần xác định |
| --- | --- |
| Debug/application log | Ngắn theo nhu cầu xử lý lỗi |
| Access/security event | Theo yêu cầu giám sát và điều tra |
| Audit trail | Theo policy kiểm toán và legal hold |
| Trace chi tiết | Thường ngắn hơn metric tổng hợp vì volume lớn |
| Aggregate metric | Theo nhu cầu capacity/trend và chi phí |
| Quarantine | Ngắn, có owner và thời hạn xử lý |
| Export/support attachment | Theo case và thời hạn được phê duyệt |

Không có con số chung phù hợp mọi tổ chức. Data owner, security, privacy/legal và compliance cần xác định thời hạn theo scope thực tế.

Archive cần storage class, encryption, access control và quy trình restore riêng. Deletion cần bao phủ primary index, replica, queue, buffer, saved query result, export, cache, archive và backup theo semantics của nền tảng. Khi backup bất biến, cần xác định thời điểm hết hạn và ngăn dữ liệu đã xóa quay lại khi restore.

Legal hold có thể tạm dừng xóa một tập dữ liệu cụ thể. Phạm vi, người phê duyệt, ngày bắt đầu/kết thúc và các bản sao liên quan phải được ghi nhận; không áp legal hold rộng vô thời hạn mà không có owner/review.

## 11. Pipeline, transport và observability vendor

Che dữ liệu ở application là lớp đầu tiên; các bước truyền và lưu cần được bảo vệ độc lập.

- TLS giữa application, agent, collector, broker và observability backend.
- Xác thực workload identity hoặc credential riêng cho từng producer.
- Phân tách quyền publish theo stream/service.
- Kiểm tra certificate và rotation.
- Private connectivity khi phù hợp với threat model/residency.
- Không dùng một API key chung cho mọi môi trường hoặc tenant.

Collector có thể buffer log khi backend mất kết nối. Buffer disk/RAM cần encryption, permission, quota, retention và xử lý khi đầy. Broker cần ACL, encryption, dead-letter policy và access audit. Parser error không được dump nguyên event có PII.

Nếu dùng SaaS, xác định region ingest/storage, support access, subprocessor, data processing terms, encryption, key options, export/deletion và breach notification. Chỉ gửi những field cần thiết. Không giả định dữ liệu đã redact ở dashboard là đã redact trước khi vendor nhận payload.

## 12. Kiểm thử redaction và access policy

Policy chỉ đáng tin khi được kiểm thử liên tục. Thay đổi schema, library logging, framework hoặc collector processor có thể tạo đường rò rỉ mới.

Automated tests cần:

- Seed canary token/email/phone trong request test và xác minh không xuất hiện ở log destination.
- Kiểm tra header/cookie/query parameter được loại bỏ.
- Kiểm tra nested JSON và exception message.
- Kiểm tra trace attributes, baggage và URL.
- Kiểm tra exporter, debug mode và fallback logging.
- Kiểm tra log parser khi schema version thêm field mới.
- Kiểm tra unauthorized user không search được restricted dataset.
- Kiểm tra export API và scheduled report cùng policy với giao diện.

Negative test phải chứng minh user được phép chỉ truy cập trong scope; user không được phép bị từ chối ở UI, API, query và export; admin không thể âm thầm tắt audit/redaction; JIT role hết hạn thì access bị thu hồi; tenant A không thể truy vấn log tenant B dù tự thay query/filter.

DLP scanner có thể nhận diện token hoặc PII theo pattern, nhưng false positive/false negative đều có thể xảy ra. Đừng dùng scanner làm control duy nhất. Kết quả phát hiện cần được xử lý mà không copy giá trị nhạy cảm vào ticket công khai.

## 13. Incident response khi dữ liệu nhạy cảm lọt vào log

Khi phát hiện secret hoặc PII trong log, không chỉ xóa một record rồi kết thúc. Cần xác định đường lan truyền và đánh giá liệu dữ liệu đã bị truy cập/export.

1. **Contain:** dừng source hoặc processor gây leak; giảm quyền truy cập; cô lập stream/index nếu cần.
2. **Classify:** xác định loại dữ liệu, mức nhạy cảm, số record, thời gian và tenant/user bị ảnh hưởng.
3. **Trace:** xác định agent, broker, destination, replica, archive, export và vendor đã nhận dữ liệu.
4. **Revoke/rotate:** nếu secret/token bị lộ, revoke hoặc rotate; invalidate session khi cần.
5. **Purge/expire:** xóa hoặc hạn chế bản ghi ở destination và bản sao trong phạm vi khả thi; xử lý backup theo policy.
6. **Assess:** xác định ai đã truy cập, alert, download hoặc share; giữ evidence điều tra có kiểm soát.
7. **Notify:** thực hiện thông báo nội bộ/khách hàng/cơ quan theo nghĩa vụ và quy trình đã xác định.
8. **Prevent recurrence:** sửa source logger, schema, collector policy và automated test; theo dõi tái phát.

Không xóa sạch audit evidence của chính sự cố. Cần lưu record điều tra đã mask và kiểm soát để chứng minh hành động khắc phục.

## 14. Ví dụ thiết kế: observability an toàn cho nền tảng đặt lịch

**Bối cảnh giả định:** Nền tảng đặt lịch có API gateway, Booking Service, Customer Service, Payment Service, message broker và managed database. Telemetry được gửi về một nền tảng observability tập trung và SIEM. Developer cần log lỗi theo service; SRE cần trace production; security analyst điều tra login và privilege event; support chỉ được xem thông tin tối thiểu của tenant được phân công. Dữ liệu gồm email, phone, booking ID, payment reference và session token.

### Thiết kế dữ liệu log

- Application log theo schema allowlist: service, environment, event, request ID, operation, status, duration và reference đã pseudonymize.
- Authorization, Cookie, password, refresh token và payment credential luôn bị drop trước ingestion.
- Email/phone không được log; nếu cần correlate, dùng opaque reference có key scope riêng.
- Payment Service log provider reference đã được phân loại; không log card data hoặc raw provider payload.
- Exception handler log error class/code; không dump request body hoặc SQL bind values.

### Pipeline

~~~mermaid
flowchart TD
    SVC["Services / Gateway"] --> SAFE["Safe structured logger"]
    SAFE --> COL["Collector: field allowlist + redaction"]
    COL --> GW["Authenticated telemetry gateway"]
    GW --> OBS["Operational observability"]
    GW --> SIEM["Security event store"]
    OBS --> DEV["Developer: service-scoped masked logs"]
    OBS --> SRE["SRE: production metrics/traces"]
    SIEM --> SEC["Security: case-scoped audit access"]
    OBS --> ARCH["Restricted archive"]
    SEC --> AUD["Independent access audit"]
~~~

### Role matrix

| Persona | Operational logs | Security/audit events | Raw restricted fields | Export |
| --- | --- | --- | --- | --- |
| Developer | Service được phân công, masked | Chỉ event liên quan nếu được duyệt | Không | Hạn chế, có audit |
| SRE | Production metrics/log/trace theo incident | Operational security signal | JIT theo case | JIT/approved |
| Security analyst | Metadata cần cho điều tra | Case-scoped | JIT theo ticket và approval | Có audit, giới hạn |
| Support | Case/tenant được phân công, masked | Không mặc định | Không | Không hoặc được duyệt |
| Auditor | Read-only evidence trong kỳ | Read-only audit scope | Không mặc định | Controlled evidence export |
| Platform admin | Quản trị pipeline/config | Audit thay đổi của platform | Không mặc nhiên được xem payload raw | Privileged, monitored |

### Retention và acceptance criteria

Data owner/security/privacy thống nhất retention theo mục đích và nghĩa vụ thực tế. Log debug có thời hạn ngắn hơn audit record; archive mã hóa và chỉ được restore theo quy trình. Access search, raw view, export, policy change và break-glass đều tạo audit event.

- Canary token và PII không xuất hiện trong operational store, trace, metric label hoặc SIEM nếu không có mục đích được phê duyệt.
- Developer chỉ search được service/environment đã phân quyền.
- Support không truy cập chéo tenant.
- Export restricted data cần approval/JIT và tạo audit event.
- Redaction policy change có review, test và version.
- Log pipeline mất kết nối không dump payload vào agent error log.
- Deletion/retention được kiểm tra trên index, archive và export workflow.

## 15. Bài thực hành: thiết kế logging bảo vệ dữ liệu nhạy cảm

**Tình huống:** Một ứng dụng thương mại điện tử ghi application log, access log, distributed trace và security audit vào một nền tảng tập trung. Log hiện có URL đầy đủ, email, user ID, session cookie và một số request body. Developer, SRE, support và security analyst dùng cùng công cụ. Dữ liệu được archive hàng tháng. Đây là dữ kiện mô phỏng.

### Nhiệm vụ

1. **Inventory:** lập danh sách nguồn telemetry, collector, broker, vendor, index, archive, export và backup.
2. **Classification:** phân loại field và xác định field cấm ghi, field cần mask/tokenize và field có thể giữ.
3. **Schema:** thiết kế structured log allowlist; định nghĩa version, correlation ID, service, environment và operation.
4. **Redaction:** áp dụng ở application, agent/collector và ingestion; thiết kế safe parser error và quarantine.
5. **Access:** tạo RBAC/ABAC matrix cho developer, SRE, support, security và auditor; tách search, raw view, export, admin và retention.
6. **Lifecycle:** định nghĩa retention, archive, deletion, legal hold và backup handling.
7. **Audit:** xác định hành động cần audit, log destination độc lập, integrity và alert.
8. **Testing:** tạo canary data, negative access tests, export tests, schema evolution tests và incident drill.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Secret canary | Gửi token giả trong Authorization header | Token không xuất hiện ở bất kỳ log destination nào |
| PII canary | Request có email/phone thử nghiệm | Field bị drop/mask theo policy |
| Nested payload | PII nằm trong object lồng nhau | Processor xử lý đúng schema hoặc reject |
| Exception leak | Database/provider exception chứa input | Log chỉ có error code/class và metadata an toàn |
| Trace baggage | Baggage chứa identifier nhạy cảm | Propagation bị chặn hoặc pseudonymize |
| Metric cardinality | User ID được thử làm label | Pipeline từ chối hoặc bỏ label |
| RBAC | Developer tìm service ngoài scope | Query bị từ chối |
| Tenant isolation | Support sửa tenant filter | Server-side policy vẫn chặn |
| Export | User tải raw restricted data | Yêu cầu approval/JIT và audit record |
| Retention | Log hết hạn | Index/archive/xuất bản sao được xử lý theo policy |
| Break-glass | SRE nâng quyền khẩn cấp | Alert, session audit, expiry và review |
| Collector failure | Processor lỗi parse event | Payload nhạy cảm không bị in ra error log |

### Deliverables

- Telemetry data-flow map và classification inventory.
- Safe logging schema và field allowlist/denylist.
- Redaction/tokenization policy có version.
- RBAC/ABAC matrix và privileged access runbook.
- Audit event schema và evidence retention plan.
- Automated test suite với canary secrets/PII.
- Incident response và deletion procedure.
- Dashboard theo dõi leak detection, access, export và policy drift.

## 16. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho log protection và access |
| --- | --- |
| **Operational Excellence** | Có schema, owner, policy version, test, access review, runbook và quy trình xử lý leak không? |
| **Security** | Data minimization, redaction sớm, IAM least privilege, tenant isolation, encryption và audit có đầy đủ? |
| **Reliability** | Redaction/filter lỗi có fail safe? Log delivery/backup/restore và audit pipeline có được giám sát? |
| **Performance Efficiency** | Masking, tokenization và policy query có overhead chấp nhận được? Sampling có giữ lại security/audit event bắt buộc? |
| **Cost Optimization** | Có giới hạn volume, cardinality, retention, archive và export? Dữ liệu nhạy cảm có bị lưu lặp không cần thiết? |
| **Sustainability** | Có tránh log payload dư thừa, trace quá chi tiết, retention vô hạn và pipeline xử lý lặp không? |

## 17. Những sai lầm thường gặp

**Chỉ che email ở giao diện.** Bản gốc vẫn có thể nằm trong storage, API, export hoặc archive.

**Ghi secret rồi kỳ vọng rotate sau.** Phải ngăn secret vào log ngay từ source; khi lộ cần incident response và revoke/rotate.

**Mask không nhất quán giữa service.** Một field bị che ở gateway nhưng lại xuất hiện trong trace của downstream.

**Dùng user/tenant identifier thô trong metric label.** Tăng cardinality và mở rộng khả năng nhận dạng.

**Cho support quyền search toàn hệ thống.** Quyền phải giới hạn theo tenant/case và được audit.

**Không tách quyền xem với quyền export.** Export tạo bản sao khó thu hồi và cần approval phù hợp.

**Không bảo vệ parser/quarantine error.** Record lỗi có thể bị dump nguyên payload vào log của collector.

**Không kiểm thử schema mới.** Field thêm sau này có thể chứa dữ liệu nhạy cảm mà policy chưa nhận diện.

**Không theo dõi redaction processor.** Processor bị tắt hoặc lỗi parse có thể khiến telemetry thô đi tiếp.

**Không xử lý backup và legal hold.** Xóa index không đồng nghĩa dữ liệu biến mất khỏi mọi bản sao.

## 18. Checklist trước khi đưa observability vào production

- [ ] Telemetry source, destination, vendor, region, archive và export path được inventory.
- [ ] Data classification bao gồm log, trace, metric, audit, collector và quarantine.
- [ ] Log schema dùng allowlist và không serialize toàn bộ request/response.
- [ ] Secret, token, credential và field nhạy cảm không cần thiết bị drop ở source.
- [ ] Masking/tokenization có mục đích, key scope và khả năng liên kết được đánh giá.
- [ ] Trace attributes, baggage, URL/query và metric label không chứa PII/secret ngoài policy.
- [ ] Redaction áp dụng nhiều lớp và có policy version/owner.
- [ ] Parser error, retry buffer và DLQ không làm lộ payload.
- [ ] RBAC/ABAC giới hạn theo role, service, environment, tenant, region và classification.
- [ ] Search, raw view, query, export, admin và retention là các quyền tách biệt.
- [ ] JIT, break-glass và vendor access có approval, expiry, session audit và review.
- [ ] Truy cập dữ liệu nhạy cảm và thay đổi policy tạo audit record được bảo vệ.
- [ ] TLS, workload identity, secret rotation và private connectivity được kiểm soát.
- [ ] Retention/archive/deletion/legal hold áp dụng cho mọi bản sao theo policy.
- [ ] Canary tests kiểm tra secret/PII không lọt vào log, trace, metric hoặc SIEM.
- [ ] Negative tests bao phủ UI, API, query và export; tenant isolation được xác minh.
- [ ] Có alert khi redaction pipeline lỗi, leak pattern xuất hiện hoặc access/export bất thường.
- [ ] Có incident runbook để contain, trace, revoke, purge, assess và prevent recurrence.
- [ ] Cost và performance của volume, masking, storage, query và retention được đo.

Log và telemetry là tài sản vận hành nhưng cũng là bản sao dữ liệu cần được bảo vệ. Hãy giảm dữ liệu ngay tại nguồn, dùng schema allowlist, che hoặc loại bỏ field nhạy cảm trước khi telemetry đi qua nhiều hệ thống, rồi giới hạn quyền xem, tìm kiếm, export và quản trị theo đúng vai trò và phạm vi. Access audit, retention, deletion, break-glass và kiểm thử tự động giúp kiểm soát tiếp tục hoạt động khi hệ thống thay đổi. Mục tiêu là giữ đủ tín hiệu để phát hiện và điều tra sự cố mà không biến nền tảng observability thành một kho dữ liệu nhạy cảm mở rộng ngoài kiểm soát.
