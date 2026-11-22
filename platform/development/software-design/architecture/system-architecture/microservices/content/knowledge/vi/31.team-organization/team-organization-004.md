# Phân biệt tự chủ nhóm với bỏ qua hợp đồng chung

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Tổ chức nhóm (Team Organization)  
> **Mục tiêu:** Hiểu ranh giới giữa quyền tự chủ kỹ thuật của một nhóm và nghĩa vụ tuân thủ những hợp đồng dùng chung; biết tổ chức ownership, chuẩn giao tiếp, quản trị thay đổi, kiểm thử tương thích và cơ chế ra quyết định giúp nhiều team phát triển nhanh mà không làm hỏng toàn hệ thống.

## 1. Tự chủ nhóm không có nghĩa “mỗi nhóm muốn làm gì cũng được”

Trong kiến trúc microservices, mỗi nhóm thường sở hữu một hoặc nhiều service và có quyền lựa chọn cách triển khai phù hợp với domain, năng lực đội ngũ và SLO. Tự chủ giúp giảm phụ thuộc lịch release, giảm phê duyệt vi mô và cho phép thay đổi cục bộ nhanh.

Tuy nhiên một service không tồn tại một mình. Nó nhận request từ API gateway, gọi service khác, phát event, dùng định danh người dùng, gửi telemetry, triển khai trên hạ tầng và xử lý dữ liệu có quy tắc bảo mật. Những điểm giao tiếp này là **hợp đồng chung** mà nhiều nhóm dựa vào để vận hành.

Ví dụ:

~~~text
             Customer-facing Application
                         |
                    API Gateway
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
      Order Team     Payment Team    Inventory Team
       Order API      Payment API     Inventory API
          |              |              |
          +--------------+--------------+
                         |
               Shared Platform Contracts
             - Identity and access model
             - API/event compatibility
             - Observability and SLO language
             - Deployment and incident behavior
             - Data handling and security rules
~~~

Order Team có thể tự chọn dữ liệu nội bộ, refactor code, thay thuật toán hoặc điều chỉnh cách scale; nhưng không thể âm thầm đổi ý nghĩa trạng thái đơn, phát event không tương thích hoặc bỏ kiểm tra authorization chỉ vì “service thuộc nhóm mình”.

**Nguyên tắc:** tự chủ là quyền quyết định **bên trong ranh giới được giao**, đồng thời chịu trách nhiệm bảo vệ **hợp đồng ở ranh giới kết nối**. Bỏ qua hợp đồng chung không phải tự chủ; đó là đẩy chi phí tích hợp và rủi ro sang người khác.

## 2. Phân biệt ba mức quyết định

Không phải mọi quyết định kỹ thuật đều cần phê duyệt toàn công ty. Điều quan trọng là phân loại phạm vi ảnh hưởng.

| Mức quyết định | Ví dụ | Cơ chế hợp lý |
|---|---|---|
| **Cục bộ, có thể đảo ngược** | Tên class, cách chia package, thuật toán nội bộ, tối ưu query không đổi contract | Nhóm tự quyết và review trong nhóm |
| **Liên nhóm, có consumer bị ảnh hưởng** | Đổi REST API, event schema, error semantics, domain model được chia sẻ | Thỏa thuận theo contract, versioning và compatibility test |
| **Toàn hệ thống/rủi ro cao** | Quy tắc định danh, phân quyền, dữ liệu nhạy cảm, disaster recovery, telemetry bắt buộc, nền tảng triển khai | Guardrails chung, owner của policy và quy trình ngoại lệ rõ |

Một quyết định có thể chuyển nhóm khi bối cảnh đổi. Ban đầu một thư viện chỉ dùng trong service A là lựa chọn cục bộ. Nếu service A bắt mọi nhóm khác dùng định dạng serialization riêng hoặc client SDK độc quyền, lựa chọn đó đã tạo ràng buộc liên nhóm và cần thương lượng.

### 2.1. Câu hỏi nhanh để phân loại

Trước khi tự quyết, nhóm hỏi:

1. Có thay đổi giao diện mà consumer khác đang dùng không?
2. Có thay đổi dữ liệu, quyền truy cập, semantics hoặc độ tin cậy mà bên khác phụ thuộc không?
3. Có gây chi phí vận hành, bảo mật, incident hoặc migration cho team khác không?
4. Có làm tăng phạm vi lỗi hoặc mất khả năng rollback toàn hệ thống không?
5. Có liên quan mục tiêu chung như audit, SLO, compliance hoặc dữ liệu khách hàng không?
6. Có thể hoàn nguyên hoàn toàn mà không cần team khác điều chỉnh không?

Nếu câu trả lời đều “không”, nhóm thường có mức tự chủ cao. Nếu một câu trả lời là “có”, cần xác định contract owner và mức phối hợp tương ứng, không mặc định phải xin phép mọi quyết định.

## 3. Định nghĩa đúng “tự chủ nhóm”

**Team autonomy** là năng lực một nhóm có đủ quyền, thông tin và trách nhiệm để thiết kế, triển khai, vận hành và cải tiến phần hệ thống mình sở hữu trong những giới hạn đã công bố.

Tự chủ thường bao gồm:
- Quyết định tổ chức code, cấu trúc module và công cụ làm việc nội bộ.
- Lựa chọn thuật toán và chiến lược lưu trữ bên trong bounded context khi đáp ứng policy.
- Quyết định nhịp release, cách thử nghiệm, feature flags và quá trình canary cho phần mình sở hữu.
- Sở hữu backlog kỹ thuật, SLO của service, runbook và vận hành production.
- Tự động hóa build, test, deploy và rollback bằng những cơ chế được hỗ trợ.
- Đề xuất cải tiến hoặc ngoại lệ đối với chuẩn chung khi có lý do và bằng chứng.

Tự chủ không có nghĩa:
- Được thay đổi public API mà không thông báo consumer.
- Được bỏ mã hóa, phân quyền hoặc audit vì muốn tăng tốc.
- Được dùng chung database của nhóm khác và sửa schema trực tiếp.
- Được ép toàn bộ team khác đổi theo cách mình muốn mà không có migration plan.
- Được tự định nghĩa lại các khái niệm nghiệp vụ dùng chung mà không thương lượng.
- Được không xử lý incident vì “lỗi nằm ở hệ thống gọi vào”.
- Được vô hạn retries/concurrency tới dependency chia sẻ.

**Quyền tự chủ phải đi cùng ownership đầu-cuối.** Một nhóm có quyền deploy độc lập nhưng mọi lỗi đều chuyển cho platform team khắc phục thì mới có quyền ra quyết định, chưa gánh đầy đủ trách nhiệm vận hành.

### 3.1. Tự chủ không đồng nghĩa cô lập tổ chức

Một nhóm có thể tham vấn, dùng thư viện chung hoặc thuê platform team xây công cụ. Những hành vi này không làm mất tự chủ nếu có lựa chọn, ranh giới dịch vụ và cơ chế phối hợp rõ. Ngược lại, cách nói “mỗi team hoàn toàn độc lập” có thể tạo lặp đầu tư, incompatibility và cognitive load quá lớn.

## 4. “Hợp đồng chung” là gì?

Hợp đồng chung là tập các cam kết mà các nhóm dựa vào khi tích hợp hoặc vận hành. Một số được diễn đạt bằng code/schema; một số bằng policy, SLO và quy trình.

| Nhóm hợp đồng | Nội dung | Người chịu ảnh hưởng |
|---|---|---|
| API contract | Đường dẫn, phương thức, kiểu dữ liệu, auth, lỗi, pagination, idempotency | Client và service gọi |
| Event contract | Tên event, schema, ordering scope, delivery semantics, compatibility | Producer, broker, consumers |
| Data contract | Owner, ý nghĩa field, classification, retention, consistency | Nguồn và tất cả bản sao |
| Identity/security contract | Workload identity, scopes, permission checks, key rotation | Tất cả service và người dùng |
| Reliability contract | Timeout/deadline, SLO, retries, rate limits, failure behavior | Caller, callee, platform |
| Observability contract | Trace context, logs, metrics, correlation, incident severity | On-call và các nhóm tích hợp |
| Deployment contract | Readiness, liveness, shutdown, rollout, rollback, migration | Platform và service owners |
| Ownership contract | API owner, DRI, escalation, incident response, change communication | Các team giao tiếp |
| Product/business semantics | Trạng thái nghiệp vụ, công thức tính, domain terminology | Product, reporting, integrations |

Không phải mọi công ty đều cần tài liệu dày cho từng mục. Hợp đồng nên **ít nhưng rõ, có thể thực thi và tương xứng rủi ro**. Một quy định mơ hồ “mọi service phải tốt và ổn định” khó dùng. Quy định cụ thể “không đưa access token vào logs và events; service phải có owner và kênh escalation” dễ kiểm chứng hơn.

### 4.1. Hợp đồng và convention khác nhau

- **Policy bắt buộc:** quy tắc không thể tự bỏ qua, thường vì bảo mật, pháp lý, correctness hoặc rủi ro chung.
- **Contract giữa producer và consumer:** cam kết về giao diện, dữ liệu, hành vi và tương thích.
- **Standard kỹ thuật:** cách làm được chọn để giảm chi phí tích hợp, có thể có ngoại lệ.
- **Convention/style:** quy ước ưu tiên để làm việc dễ dàng; tác động cục bộ thấp.
- **Guideline/recommendation:** thực hành nên áp dụng nếu phù hợp, không nhất thiết là bắt buộc.

Nếu mọi guideline đều được gọi là “bắt buộc”, số ngoại lệ và sự chống đối tăng; nếu mọi policy đều chỉ là “gợi ý”, an toàn và tính tương thích sẽ không được bảo vệ.

## 5. Liên hệ với bounded context và quyền sở hữu domain

Trong Domain-Driven Design, **bounded context** là ranh giới trong đó một mô hình nghiệp vụ có ý nghĩa nhất quán. Một term có thể có ý nghĩa khác nhau trong các context.

Ví dụ “Customer” ở:
- Sales: người có tiềm năng mua hàng.
- Billing: chủ thể nhận hóa đơn.
- Fulfillment: người nhận hàng.
- Support: người liên hệ để giải quyết yêu cầu.

Không nên ép tất cả service dùng một object Customer chung chứa mọi field và semantics, vì sẽ tạo shared model chặt và làm các team phải deploy cùng nhau.

### 5.1. Tách domain autonomy khỏi integration contract

Bên trong Billing, nhóm có thể lưu BillingAccount, InvoiceRecipient hoặc TaxProfile theo mô hình riêng. Khi giao tiếp với Order, Billing công bố hợp đồng như:

~~~text
POST /billing/invoices
Request: orderRef, payerRef, invoiceItems, currency
Response: invoiceRef, invoiceStatus
~~~

Order không cần truy cập bảng invoice_line nội bộ của Billing. Billing có thể refactor storage mà không bắt Order cập nhật, **miễn giữ API contract và semantics đã thỏa thuận**.

Một schema nội bộ không nên vô tình trở thành public contract qua:
- Dùng chung entity ORM.
- Truy vấn trực tiếp DB của service khác.
- Chia sẻ Java model library mà không versioning.
- Serializing toàn bộ aggregate ra event.
- Để consumer phụ thuộc tên topic/table không được công bố.

### 5.2. Conway's Law và thiết kế ranh giới nhóm

Cấu trúc giao tiếp của tổ chức có xu hướng phản ánh vào kiến trúc phần mềm. Nếu một tính năng luôn cần bốn nhóm chỉnh cùng một bảng hoặc release cùng lúc, có thể ranh giới service/team chưa phù hợp.

Tuy nhiên không thể sửa mọi vấn đề bằng việc “mỗi team một microservice”. Quá nhiều service nhỏ làm tăng network, observability, on-call và coordination cost. Cân nhắc:
- Domain ownership.
- Nhịp thay đổi và nhu cầu release độc lập.
- Mức coupling giữa features.
- Năng lực vận hành của team.
- Chi phí giao tiếp và cognitive load.
- Data consistency và transaction boundaries.

Một **modular monolith** với ownership rõ có thể tự chủ đủ tốt ở giai đoạn phù hợp. Số lượng microservice không phải thước đo tự chủ.

## 6. Quyền tự quyết nội bộ và trách nhiệm ở ranh giới API

### 6.1. Những thay đổi thường được phép độc lập

Nếu Payment Service thay:
- Cấu trúc package Java.
- ORM framework hoặc JDBC implementation.
- Index nội bộ.
- Thuật toán fraud scoring không thay kết quả công bố.
- Cách batch truy vấn.
- Cách triển khai nội bộ trong SLO đã thỏa thuận.

Nhóm có thể tự quyết và deploy riêng, miễn không vi phạm yêu cầu bảo mật, dữ liệu, tính đúng đắn và vận hành.

### 6.2. Những thay đổi không được âm thầm thực hiện

Ví dụ Payment API hiện trả:

~~~json
{
  "paymentId": "pay-123",
  "status": "AUTHORIZED",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

Một nhóm muốn đổi status “AUTHORIZED” thành “PAID” mà không thông báo. Consumer Order có thể đang hiểu AUTHORIZED là **đã giữ quyền thanh toán nhưng chưa capture**. Đổi từ có thể biến một quyết định nghiệp vụ khác thành cùng một enum, gây sai kết quả.

Tương tự:
- Xóa field mà client vẫn cần.
- Đổi nghĩa amount từ minor units sang decimal mà vẫn giữ tên.
- Đổi mã lỗi retryable sang lỗi permanent mà không cập nhật hợp đồng.
- Trả 200 “accepted” thay vì “completed” mà không phân biệt.
- Bỏ idempotency trên POST tạo charge.
- Giảm quota từ 200 req/s xuống 20 req/s mà không có lộ trình.
- Thay auth scopes hoặc audience mà consumer chưa sẵn sàng.

**Cốt lõi:** contract không chỉ là JSON shape; nó gồm cả **semantics, security, timeouts và error behavior**.

### 6.3. Contract-first không có nghĩa tất cả nhóm phải họp mọi lần

Có thể dùng OpenAPI/AsyncAPI/Protobuf/schema registry và pull request để các bên review async. Với thay đổi backward-compatible, quá trình có thể tự động hóa và deploy độc lập; chỉ thay đổi rủi ro cao hoặc breaking change mới cần phối hợp chặt.

## 7. Versioning và backward compatibility

Một nhóm có thể thay service bao nhiêu lần tùy nhu cầu, nhưng không được khiến consumer bị hỏng ngoài kế hoạch.

### 7.1. Tương thích không chỉ ở compile time

Ví dụ một field mới được thêm vào JSON response thường là non-breaking đối với client bỏ qua unknown fields; nhưng:
- Client strict parser có thể từ chối unknown fields.
- Field mới có thể làm payload vượt giới hạn.
- Semantic thay đổi dù schema vẫn giống.
- Endpoint trả dữ liệu nhạy cảm mới làm rộng phạm vi thông tin.
- Enum mới có thể làm client throw nếu switch không có default.
- Thay đổi thứ tự hoặc ordering trong list có thể làm client sai.

Vì vậy “thêm field” không **tự động** an toàn tuyệt đối. Cần biết client behavior và test contract thực.

### 7.2. Mẫu expand-and-contract

Khi cần đổi một API hoặc event:

~~~text
Phase 1 — Expand
  Producer hỗ trợ cả cấu trúc cũ và mới
  Consumer cũ vẫn hoạt động

Phase 2 — Migrate
  Consumer chuyển sang cấu trúc mới
  Theo dõi mức sử dụng cấu trúc cũ

Phase 3 — Contract
  Xác nhận không còn consumer phụ thuộc cũ
  Remove/deprecate theo chính sách
~~~

Ví dụ đổi field userId thành customerRef:
1. Producer phát cả hai trong thời gian chuyển tiếp, có semantics rõ.
2. Consumer update để đọc customerRef.
3. Theo dõi consumer versions/contract tests.
4. Xóa userId khi tất cả bên nhận đã sẵn sàng và retention/replay không còn đòi schema cũ.

Với event streaming, consumer replay lịch sử có thể vẫn thấy event schema cũ sau nhiều tháng. Cần versioned deserialization hoặc migration thay vì giả định “sau một ngày không còn event cũ”.

### 7.3. Không ép lockstep deployment

Nếu Order v2 chỉ hoạt động khi Payment v2 đã deploy cùng giây, tính độc lập đã giảm. Chọn compatibility window để **old producer + new consumer** và **new producer + old consumer** hoạt động theo chiều cần thiết cho rollout.

Trong các migration lớn, có thể cần kế hoạch từng bước. Tự chủ không phải cấm phối hợp, mà là giảm các lần buộc mọi service đổi cùng lúc.

### 7.4. Consumer-driven contract testing

Provider có thể chạy bài kiểm thử thể hiện kỳ vọng thực của consumer:
- Field bắt buộc.
- Kiểu dữ liệu và enum.
- Error code và retry semantics.
- Authorization behavior.
- Idempotency behavior.
- Version compatibility.

Consumer-driven contract không thay thế tất cả integration/E2E tests; nó giảm rủi ro provider đổi mà không biết ai phụ thuộc. Contract phải do các bên đồng ý, không biến mỗi consumer thành người veto mọi refactor nội bộ.

## 8. Event-driven architecture: tự chủ nhưng không tự do phá schema

Trong hệ thống phát event:

~~~text
Order Producer
    |
    v
OrderCreated topic
    |
    +--> Inventory Consumer
    +--> Analytics Consumer
    +--> Notification Consumer
~~~

Producer sở hữu ý nghĩa event và hợp đồng publish; consumer được tự triển khai xử lý bên trong. Nhưng nếu producer thay eventType, xóa orderRef hoặc đổi ordering scope, các consumer có thể lỗi âm thầm.

### 8.1. Contract event cần chứa gì?

- Event name/semantics và owner.
- Schema, version, field types, required/optional.
- Correlation/event ID và dedup semantics.
- Ý nghĩa timestamp và source commit boundary.
- Ordering guarantee theo key/partition/aggregate.
- Delivery assumption: at-least-once, possibility of duplicates.
- Retention/replay policy.
- Classification dữ liệu và consumer được phép.
- Quy tắc thay đổi field và deprecation.
- Cách xử lý schema không tương thích, retry/DLQ.

Một service không được tự phát toàn bộ ORM entity vì “consumer cần gì thì đọc”. Điều đó biến storage model thành public payload và có thể lan dữ liệu nhạy cảm.

### 8.2. Không giấu lỗi bằng DLQ

Nếu producer đổi schema và consumer cũ đẩy tất cả message vào DLQ, producer vẫn có thể thấy publish success. Hợp đồng chung đã bị phá, dù “mỗi team deploy độc lập”. Đo consumer deserialization failures, lag, DLQ và business completion trước khi coi rollout thành công.

### 8.3. Event ownership không có nghĩa producer quyết định mọi mục đích sử dụng

Consumer có thể tạo derived data và read model riêng, nhưng phải tuân thủ classification, retention và allowed purpose. Consumer không được tự lưu thêm email/phone từ một event mà không có quyền và mục đích, chỉ vì về kỹ thuật đọc được.

## 9. Dữ liệu: sở hữu database riêng nhưng vẫn có ranh giới chung

“Database per service” thường giúp giữ ownership và tránh coupling qua schema. Tuy nhiên nó không tự giải quyết:
- Data residency.
- Quyền riêng tư và retention.
- Deletion/correction xuyên projection.
- Consistency giữa các luồng.
- Quyền export và analytics.
- Encryption/backup.
- Hợp đồng sự kiện.

### 9.1. Tránh shared database như một lối tắt

Nếu Inventory có thể chạy SQL UPDATE trực tiếp vào Order DB, Order Team không còn tự do refactor bảng hoặc thay storage. Tác động còn ảnh hưởng transaction invariants, audit và quyền truy cập.

Ưu tiên API, event hoặc hợp đồng data-sharing được quản trị. Nếu legacy cần truy cập trực tiếp tạm thời, đánh dấu đây là ngoại lệ có owner, thời hạn và kế hoạch loại bỏ; không hợp thức hóa như mặc định.

### 9.2. Không nhân bản dữ liệu nhạy cảm vô điều kiện

Order Service có thể chỉ cần customerRef, không cần full customer profile. Nếu Notification cần email, cân nhắc gửi lệnh cho service sở hữu liên hệ thay vì phát email qua mọi event. Data minimization giúp giảm số bản sao mà từng team phải quản lý.

Tự chủ nhóm không cho phép bỏ qua chuẩn classification, retention, access logging hoặc quy trình xóa chỉ vì bản sao nằm trong database riêng.

### 9.3. Shared semantic definitions

Một chỉ số như “active customer”, “successful order” hoặc “net revenue” cần semantics rõ khi nhiều team cùng báo cáo. Billing có thể có trạng thái “invoice issued”, Payment có “funds captured”, Order có “order confirmed”. Nếu mọi team tự gọi tất cả là “paid”, dashboard có thể mâu thuẫn.

Hợp đồng semantic nên định nghĩa:
- Thuật ngữ domain chính thức và ngữ cảnh.
- Sự kiện làm thay đổi trạng thái.
- Điều kiện bao gồm/loại trừ.
- Chủ sở hữu chỉ số.
- Version khi định nghĩa thay đổi.
- Cách reconcile dữ liệu giữa service.

Không ép mọi bounded context dùng cùng class; thống nhất **tại điểm trao đổi ý nghĩa**.

## 10. Bảo mật là guardrail chung, không phải lựa chọn tùy ý

Một service có thể tự chọn framework hoặc implementation của authentication/authorization theo nền tảng được phép, nhưng phải đáp ứng policy như:
- Xác minh caller identity và audience/issuer khi áp dụng.
- Phân quyền theo action và resource, không chỉ endpoint.
- Tenant isolation.
- Least-privilege workload identity.
- Secret management và rotation.
- Không log access token, password hoặc private key.
- Mã hóa dữ liệu nhạy cảm khi lưu và truyền theo yêu cầu.
- Audit những thao tác có rủi ro.
- Quản trị dependency vulnerabilities.
- Tuân thủ data retention/export restrictions.

Không có chuẩn chung, mỗi team có thể vô tình xây một biến thể “JWT đã được ký là được phép đọc mọi customerId”, tạo lỗ hổng giữa service dù từng nhóm nghĩ mình làm đúng.

### 10.1. Tự chủ với security implementation

Một team có thể tự viết module policy phù hợp domain, nhưng phải thỏa contract về caller identity, resource authorization, audit và cách fail-safe. Platform team có thể cung cấp SDK/middleware mặc định để giảm sai sót; nhóm vẫn sở hữu logic domain-specific như “người bán chỉ được sửa sản phẩm của shop mình”.

### 10.2. Bảo mật phải có chốt kiểm tự động

Ví dụ pipeline có thể chặn:
- Secret xuất hiện trong repo.
- Container chạy với đặc quyền không được phép.
- Image có lỗ hổng vượt ngưỡng policy khi chưa có ngoại lệ.
- Service thiếu cấu hình TLS bắt buộc.
- Endpoint nhạy cảm không có authorization test.
- Event chứa field RESTRICTED ngoài contract.

Không nên biến mọi commit thành cuộc họp security review, nhưng cũng không biến kiểm soát bắt buộc thành tài liệu wiki không ai thực thi.

## 11. Reliability và SLO: mỗi nhóm sở hữu service nhưng cùng chia sẻ failure domain

Giả sử Order gọi Payment và Inventory. Payment Team có thể tự quyết cách scale; nhưng Order Team cần biết reliability contract:

- Tốc độ phục vụ có thể duy trì.
- Request deadline và timeout.
- Rate/concurrency limits.
- HTTP/gRPC status và error semantics.
- Retryable vs permanent failures.
- Idempotency guarantees.
- Cách degrade hoặc fail closed.
- SLO/SLI và cửa sổ đo.
- Khi dependency lỗi, kênh thông báo và incident ownership.

### 11.1. Không tự tăng retry vào dependency chia sẻ

Nếu mỗi Order replica retry 5 lần khi Payment chậm, Payment có thể nhận nhiều lần tải ban đầu, phá SLO của nhóm khác cũng dùng Payment. Đây là một sự can thiệp xuyên team dù chỉ sửa một config file trong Order.

Vì vậy cần contract về:
- Retry budget.
- Max concurrency.
- Backoff với jitter.
- Deadline propagation.
- Rate limit và response cho overload.
- Circuit breaker/half-open behavior.
- Idempotency key cho side effect.

Một team có quyền tự thực thi những cơ chế này nhưng **không có quyền đẩy vô hạn tải vào hệ thống của team khác**.

### 11.2. Ví dụ ngân sách concurrency

Payment chịu khoảng 200 calls/s cho toàn cluster theo thỏa thuận. Nếu có 20 Pod Orders, mỗi Pod đặt limiter 200 calls/s thì tải tiềm năng là 4.000 calls/s, vượt rất xa contract.

Cần global quota hoặc phân bổ ngân sách theo số replica, cùng headroom cho các consumer khác. Contract không chỉ là “endpoint hoạt động”, mà còn gồm **giới hạn tài nguyên dùng chung**.

### 11.3. SLO đầu-cuối khác SLO cục bộ

Tất cả service có thể đạt 99,9% availability riêng nhưng luồng đồng bộ bắt buộc đi qua nhiều dependency vẫn có availability thấp hơn, tùy tính tương quan và cách degrade. Tự chủ nhóm phải gắn với **business workflow SLO** và trách nhiệm điều tra qua nhiều service, không chỉ dashboard đẹp của một Pod.

## 12. Observability: tiêu chuẩn tối thiểu để cùng vận hành

Nếu mọi team tự đặt tên field log và correlation ID khác nhau, incident xuyên service sẽ khó điều tra.

Một hợp đồng quan sát chung nên xác định:
- Trace context propagation qua HTTP/gRPC và message broker.
- Correlation ID hoặc business reference theo cách không lộ PII.
- Structured logs: timestamp, service, environment, error class, request/event reference.
- Metrics đặt tên/đơn vị theo convention, cardinality có giới hạn.
- Error classification và severity.
- SLO/SLI definitions.
- Retention và redaction.
- Tài liệu dashboard, alert và runbook.
- On-call owner và escalation path.

Điều này không có nghĩa mọi nhóm dùng cùng ngôn ngữ lập trình hoặc chung một library logging không được thay. Họ có thể dùng adapter/SDK tương thích với contract telemetry.

### 12.1. Tín hiệu chuẩn giúp tự chủ thật hơn

Nếu service A luôn xuất trace và metric tương thích, Order Team không cần hỏi team A mỗi lần một request timeout. Tương tự, nếu mọi service có readiness, deploy metadata và runbook chuẩn, platform/on-call có thể quan sát mà không cần kiến thức riêng từ tác giả code.

### 12.2. Log contract là ranh giới bảo mật

Việc debug không phải ngoại lệ cho phép in toàn bộ payload nhạy cảm. Shared contract phải kiểm soát PII, secrets, request bodies, sampling và data retention. Nhóm có thể thêm log domain riêng nhưng không được đưa dữ liệu cấm vào observability stack chung.

## 13. Deployment autonomy cần platform contract ổn định

Một team muốn deploy độc lập phải có một giao diện rõ với platform:
- Artifact/image format và provenance.
- Build and test gates.
- Health/readiness/liveness/startup semantics.
- Resource requests/limits.
- Secret/config injection.
- Graceful shutdown và connection draining.
- Rollout/canary/rollback.
- Database schema migration và version compatibility.
- Observability hooks.
- Incident rollback ownership.

Với Kubernetes, platform có thể cung cấp chart/template và policy; team chỉ cần khai báo tham số service phù hợp. Đây là **paved road / golden path**: đường chuẩn dễ đi nhất nhưng không nhất thiết cấm mọi ngoại lệ.

### 13.1. Không giao quyền deploy mà thiếu quyền vận hành

Nếu team tự merge và deploy nhưng không biết rollback, không có alert, không hiểu quota và không có quyền xem telemetry, quyền tự chủ chỉ là hình thức. Nên thiết kế self-service:
- Xem cấu hình hiệu lực an toàn.
- Tự canary/rollback trong phạm vi service.
- Xem latency, errors, saturation, traces.
- Quản lý feature flag theo policy.
- Được cấp quyền tạo môi trường thử nghiệm phù hợp.
- Có tài liệu và contact rõ cho vấn đề platform.

### 13.2. Cơ chế ngoại lệ có thời hạn

Không phải service nào cũng giống nhau: một streaming worker có thể cần graceful shutdown khác API ngắn. Thay vì buộc dùng template sai hoặc để nhóm bỏ qua chuẩn, tạo **exception process**:
- Lý do và yêu cầu khác biệt.
- Rủi ro và điều kiện bảo vệ tương đương.
- Owner và người chấp thuận.
- Phạm vi service/môi trường.
- Thời hạn hoặc điều kiện đánh giá lại.
- Tài liệu vận hành và kiểm thử.
- Kế hoạch quay về chuẩn nếu phù hợp.

Ngoại lệ có kiểm soát là một phần của tự chủ; ngoại lệ bí mật, không owner và không hết hạn là nợ vận hành.

## 14. Shared libraries: tái sử dụng có thể giúp hoặc cản trở tự chủ

Một thư viện chung cho authentication, telemetry, HTTP client hoặc schema có thể giảm chi phí. Nhưng nếu mọi service phải nâng version library cùng lúc, cả hệ thống có thể rơi vào **lockstep release**.

### 14.1. Khi nên chuẩn hóa thành library

- Logic bảo mật hoặc protocol cần thực hiện nhất quán.
- Cross-cutting concern có API ổn định và nhiều team hưởng lợi.
- Một bug fix chung có thể phân phối độc lập.
- Compatibility và versioning có thể quản lý rõ.
- SDK có tài liệu, owner, test và support.

### 14.2. Khi nên tránh shared domain model

Một package chứa các class Customer, Order, Invoice với field của mọi team làm ranh giới domain bị hòa trộn. Bất cứ ai thay Customer đều có thể buộc tất cả ứng dụng rebuild và release.

Thay bằng:
- Contract schemas riêng tại boundary.
- DTO/client API có version độc lập.
- Domain model nội bộ theo bounded context.
- Mapping rõ ràng giữa external DTO và internal entity.

### 14.3. Đừng biến library thành cách áp đặt bí mật

Một team có thể cung cấp thư viện tiện lợi nhưng không mặc định có quyền thay runtime behavior của tất cả service. Library change cần changelog, compatibility, test và rollout policy, đặc biệt nếu chứa retry defaults hoặc security behavior.

## 15. Vai trò của Platform Team và Enabling Team

Một platform team hiệu quả tạo **năng lực dùng chung như một sản phẩm nội bộ**: build/deploy pipeline, observability, secrets, identity integration, templates, self-service environments. Nó giảm cognitive load để stream-aligned teams tập trung nghiệp vụ.

Platform Team không nên trở thành nút thắt cấp quyền cho mọi dòng code. Những hoạt động phù hợp:
- Công bố API/platform contract có version.
- Cung cấp golden path với tài liệu và ví dụ.
- Chạy linter/policy tests trong CI.
- Đo developer experience và thời gian từ ý tưởng đến production.
- Tư vấn service có nhu cầu ngoại lệ.
- Vận hành platform SLO và incident thuộc platform.

**Enabling Team** hỗ trợ kiến thức, đào tạo và hướng dẫn (security, reliability, architecture), giúp các team tự thực thi. Không nên biến coaching thành approval gate vô thời hạn.

### 15.1. Tránh hai cực đoan

**Cực đoan 1: Centralized architecture board quyết mọi thứ.** Hầu hết quyết định nhỏ phải chờ, release chậm, team mất ownership và không học từ thực tế.

**Cực đoan 2: Không có chuẩn chung.** Mỗi team một cách identity, logging, API error, schema, deployment; integration và incident cost phình to.

Mô hình cân bằng là **federated governance với guardrails rõ, thực thi tự động và trách nhiệm phân tán**.

## 16. Mô hình quyết định: local-first, contract-aware

Có thể lập ma trận:

| Quyết định | Nhóm sở hữu tự quyết? | Cần phối hợp? |
|---|---|---|
| Refactor package nội bộ | Có | Không, nếu không đổi contract |
| Thay query plan/index | Có | Nếu shared DB/resources hoặc migration có rủi ro |
| Nâng library nội bộ | Có | Nếu thay interoperability/security policy |
| Thêm endpoint chỉ nội bộ nhóm | Có, theo guardrail | Nếu phát hành cho consumer khác |
| Thêm optional response field | Thường có | Contract validation và xem dữ liệu nhạy cảm |
| Xóa/đổi nghĩa field đang dùng | Không đơn phương | Có migration và consumer sign-off |
| Đổi tên event/enum semantics | Không đơn phương | Producer/consumer review |
| Bỏ mTLS hoặc audit | Không | Policy owner, ngoại lệ nếu được phép |
| Tăng retry tới shared dependency | Không vô giới hạn | Dependency owner/capacity contract |
| Dùng framework khác | Có thể | Nếu vẫn đáp ứng platform/security/ops requirements |
| Tách DB riêng cho bounded context | Có thể | Data migration, retention, access, cross-context |
| Đổi toàn tổ chức sang một tracing schema mới | Không đơn phương | Platform/observability owners |
| Thay thuật ngữ business được dùng trong analytics | Không đơn phương | Domain owners và data consumers |
| Tự chọn sprint planning process | Có | Chỉ khi có phụ thuộc release/incident xuyên team |

Mục tiêu của ma trận là làm rõ **ai được quyết gì**. Không dùng ma trận như cớ để chặn mọi cải tiến vì “có thể ảnh hưởng” theo nghĩa mơ hồ. Với thay đổi có ảnh hưởng, hãy xác định người nhận, migration path và bằng chứng tương thích.

## 17. Architectural Decision Record (ADR) và RFC

ADR ghi lại **vì sao** chọn một quyết định quan trọng, không chỉ code cuối cùng. Một ADR ngắn có thể gồm:

~~~text
ADR-017: Order service adopts PostgreSQL
Status: Accepted
Context:
  Orders needs transactional writes and query patterns X/Y.
Decision:
  Use PostgreSQL for Order's internal state.
Constraints:
  Must meet backup, encryption, observability and deletion policies.
Alternatives:
  Existing shared database; document store.
Consequences:
  Team owns migrations, pool sizing and operational runbook.
Contract impact:
  No changes to public API/event schemas.
Review trigger:
  Workload or SLO changes substantially.
~~~

Với quyết định liên nhóm, dùng RFC để thu thập ý kiến trong thời hạn rõ:

~~~text
Problem and goals
Non-goals
Affected contracts and consumers
Options and trade-offs
Security/data/reliability impact
Compatibility and migration plan
Rollout, observability and rollback
Owners/DRIs
Decision deadline and escalation
~~~

**Không cần ADR cho mọi tên biến.** Chỉ tạo khi quyết định có tác động đáng kể, khó đảo ngược, liên quan policy, hoặc cần hiểu trong tương lai. Tài liệu phải ngắn, có owner và ở gần workflow phát triển.

### 17.1. Phối hợp bất đồng không phải đồng thuận vô hạn

Một RFC không nên bị giữ mở vì mọi người có sở thích khác nhau. Cần:
- Decision owner rõ.
- Tiêu chí kỹ thuật và business.
- Thời hạn phản hồi.
- Người có quyền quyết cuối cùng trong phạm vi đó.
- Đường escalation khi có xung đột policy hoặc rủi ro liên team.
- Ghi nhận ý kiến khác biệt và lý do chọn phương án.

Đối với policy an toàn bắt buộc, không đơn giản bỏ qua người sở hữu policy. Đối với lựa chọn cục bộ đã đáp ứng contract, team khác không có quyền veto chỉ vì họ thích framework khác.

## 18. RACI/DRI để tránh vùng trách nhiệm trống

**DRI (Directly Responsible Individual/Owner)** là người/nhóm chịu trách nhiệm dẫn dắt một quyết định hoặc kết quả. **RACI** là cách mô tả Responsible, Accountable, Consulted và Informed. Tên cụ thể có thể đổi theo tổ chức, nhưng cần một nơi quy trách nhiệm rõ ràng.

Ví dụ cho một thay đổi Payment API:

| Hoạt động | Payment Team | Order Team | Platform | Security |
|---|---|---|---|---|
| Thiết kế API contract | Chịu trách nhiệm chính | Tham vấn với tư cách consumer | Nếu liên quan gateway | Nếu auth/data nhạy cảm |
| Thiết kế implementation nội bộ | Tự chủ | Không cần phê duyệt | Cung cấp runtime/tooling | Guardrail khi áp dụng |
| Kiểm compatibility | Chạy provider tests | Cung cấp consumer expectations | CI hỗ trợ | Test policy cần thiết |
| Deploy Payment | Chủ động trong policy | Nhận thông tin nếu ảnh hưởng | Platform deploy system | Theo dõi rủi ro nếu cần |
| Incident Payment outage | Primary owner | Hỗ trợ end-to-end workflow | Hỗ trợ hạ tầng | Hỗ trợ security incident |
| Breaking migration | Dẫn dắt kế hoạch | Cập nhật client trong window | Hỗ trợ orchestration | Review nếu thay policy |

Một vấn đề phổ biến là “ai cũng được tham vấn, không ai accountable”. Cần xác định contract owner, service owner và decision owner khác nhau nếu phạm vi công việc thực sự khác.

### 18.1. Ownership cần theo sản phẩm và vòng đời

Mỗi service nên có:
- Maintainer/team owner.
- Public contract và version.
- SLO/SLI owner.
- On-call escalation.
- Data owner/processing purpose khi phù hợp.
- Runbook và rollback.
- Dependency list, rate/concurrency budgets.
- Lifecycle: active, deprecated, retirement plan.

Nếu người viết ban đầu đã rời nhóm, ownership vẫn phải chuyển giao. “Không ai quản API cũ” là nguồn phá hợp đồng lâu dài.

## 19. Hợp đồng kỹ thuật phải được kiểm chứng tự động

Tài liệu rất hữu ích nhưng không đủ. Một số **architecture fitness functions** có thể chạy liên tục trong CI/CD để biến guardrail thành bằng chứng.

Ví dụ:
- OpenAPI diff phát hiện breaking change.
- Consumer contract tests kiểm response shape/behavior.
- Schema registry compatibility check.
- Secret scanning và dependency policy.
- Kiểm tra log không chứa raw tokens/PII trong case test.
- Kubernetes policy kiểm resource limits, security context.
- Smoke tests cho readiness và graceful shutdown.
- API authentication/authorization integration tests.
- Linter xác thực HTTP error envelope theo convention.
- Telemetry checks cho trace context và service metadata.
- Database migration compatibility test khi deploy phiên bản cũ/mới chồng lấn.
- Data contract check cho fields được phép xuất.

Một fitness function cần có:
1. Quy tắc nào được kiểm?
2. Ai là policy owner?
3. Kiểm ở đâu (commit, build, deploy, runtime)?
4. Hành vi khi fail (block, warn, exception)?
5. Cách xin ngoại lệ có deadline?
6. Cách kiểm false positive và nâng cấp rule?

**Automated gate không phải lý do bỏ qua review nghiệp vụ.** Công cụ nhận ra field bị xóa nhưng không luôn biết semantic “AUTHORIZED” đổi nghĩa. Kết hợp test máy và ownership của người.

## 20. Governance theo guardrail thay vì gate

Một **gate** yêu cầu hỏi người phê duyệt tại từng bước. Một **guardrail** cho phép nhóm đi nhanh trong giới hạn an toàn đã công bố, với phản hồi tự động khi ra ngoài.

Ví dụ:

~~~text
Propose local service change
           |
           v
Automated checks: tests, security, API diff, data policy
           |
           +-- Within agreed guardrails
           |         |
           |         v
           |   Team can deploy independently
           |
           +-- Contract impact or policy exception
                     |
                     v
            Review affected owners
                     |
                     v
            Migration/exception decision
                     |
                     v
              Controlled rollout
~~~

Cách làm này bảo vệ khả năng tự chủ:
- Đường chuẩn phải dễ dùng hơn đường đi vòng.
- Một thay đổi cục bộ không đợi kiến trúc board.
- Breaking change có quy trình và deadline.
- Ngoại lệ được phép khi có bằng chứng.
- Policy được version và thay đổi có thông báo.
- Team có thể tự đo xem họ đã đáp ứng quy tắc hay chưa.

### 20.1. “Golden path” là sản phẩm, không phải mệnh lệnh trống

Đường chuẩn tốt có:
- Template service phù hợp.
- CI/CD sẵn.
- Identity/secret/telemetry tích hợp.
- Health checks và graceful shutdown.
- Ví dụ contract API/event.
- Cơ chế self-service.
- Tài liệu migration, troubleshooting.
- Kênh feedback và versioning.

Nếu template quá khó hoặc không đáp ứng use case, các team sẽ copy/paste, fork và tạo biến thể riêng. Platform team nên đo adoption, developer lead time, support burden và tỷ lệ ngoại lệ để cải tiến.

## 21. Hợp đồng chung cũng có chi phí, phải giữ tối thiểu

Quá nhiều chuẩn có thể cản trở đổi mới. Ví dụ bắt mọi team dùng cùng một ORM, framework, cấu trúc thư mục và chiến lược cache dù workload khác nhau sẽ tạo chi phí mà không có lợi ích liên service tương xứng.

Một chuẩn chung nên tồn tại khi ít nhất một lý do rõ:
- Bảo vệ rủi ro nghiêm trọng: security, privacy, correctness.
- Giảm đáng kể chi phí tích hợp/on-call.
- Duy trì interoperability hoặc khả năng migration.
- Giảm cognitive load bằng nền tảng dùng chung.
- Bảo vệ một tài nguyên/quota chung.
- Tăng chất lượng bằng automation giá rẻ.

Nếu chỉ là sở thích của một nhóm, nên giữ ở dạng recommendation.

### 21.1. Chi phí cơ hội của tính nhất quán

“Thống nhất” không luôn đồng nghĩa “hiệu quả”. Một service analytics batch có thể dùng stack khác với request-serving JVM service. Nếu vẫn đạt identity, data, telemetry, deployment và support contract, cho phép khác biệt có thể là lựa chọn đúng.

Mục tiêu không phải đồng nhất toàn bộ công nghệ; mục tiêu là **tương thích ở ranh giới và dễ vận hành ở quy mô tổ chức**.

## 22. Thay đổi một contract đã có nhiều consumers

Một runbook ngắn:

1. **Inventory:** tìm tất cả consumer đã đăng ký hoặc có bằng chứng dùng thực tế, gồm external clients, async workers và batch.
2. **Characterize:** phân biệt field bắt buộc, semantics, error handling, schema version, security/purpose.
3. **Classify impact:** additive, behavior-changing, breaking hay security-sensitive.
4. **Propose migration:** dual-format, versioned endpoint, schema evolution, feature flag hoặc adapter.
5. **Agree rollout window:** provider và consumers chấp thuận kế hoạch, owner, deadline.
6. **Automate compatibility:** provider/consumer tests và contract diff.
7. **Deploy expand phase:** hỗ trợ cả hành vi cũ và mới; không cắt client chưa sẵn sàng.
8. **Observe usage:** traffic theo version, consumer errors, DLQ, p99 và business outcomes.
9. **Migrate consumers:** deploy từng nhóm theo thời hạn, có rollback.
10. **Retire old contract:** chỉ khi đã có bằng chứng có thể bỏ, kể cả event lịch sử/replay.
11. **Document decision:** cập nhật ADR, API docs, deprecation notice và owner.

Khi không biết tất cả consumer vì có event bus quá mở hoặc client không đăng ký, **đó là nợ quản trị contract cần sửa**; không mặc định không ai dùng field cũ.

### 22.1. Ví dụ đổi tiền tệ và đơn vị

Payment API v1 trả amount=1000 theo minor units. Một team muốn đổi sang decimal amount=10.00 để “dễ đọc”. Nếu giữ tên field và endpoint, consumer có thể nhân/chia sai 100 lần.

Thiết kế migration:
- Giữ amountMinor ở API cũ.
- Thêm field mới amountDecimal với type/semantics rõ nếu thực sự cần.
- Version schema hoặc endpoint khi có breaking semantics.
- Test trên currencies có số chữ số thập phân khác nhau.
- Giữ compatibility window và giám sát consumer adoption.
- Chỉ deprecate field cũ sau khi các client đã chuyển.

Đây là ví dụ minh họa rủi ro semantic, không phải khuyến nghị bắt mọi API thanh toán dùng một kiểu số duy nhất. Hợp đồng phải rõ cách biểu diễn tiền, làm tròn và nguồn dữ liệu.

## 23. Khi các team xung đột mục tiêu

### 23.1. Order muốn độ trễ thấp, Payment cần kiểm soát rủi ro

Order đề nghị Payment bỏ kiểm tra fraud để giảm 150 ms. Payment từ chối vì kiểm tra là ràng buộc bảo mật/nghiệp vụ. Đây không phải lỗi thiếu tự chủ của Order; đó là xung đột mục tiêu cần giải ở cấp business/risk owner.

Hướng đúng:
- Làm rõ SLO end-to-end.
- Đo chi phí từng bước.
- Tối ưu fraud implementation hoặc kiến trúc async nếu phù hợp.
- Giữ điều kiện rủi ro bắt buộc.
- Ghi quyết định về latency/correctness rõ ràng.

### 23.2. Analytics muốn mọi event chứa toàn bộ customer profile

Analytics muốn giảm coupling và dễ làm báo cáo, nhưng full profile làm rộng phạm vi dữ liệu nhạy cảm. Product owner/data owner cần xác định trường được phép và use case. Có thể tạo view/aggregate/projection chuyên dụng thay vì nhét toàn bộ dữ liệu vào generic events.

### 23.3. Platform muốn mọi team dùng một runtime

Platform có thể đưa ra lý do support cost, security patch và operational efficiency. Một nhóm có thể có workload đặc biệt cần runtime khác. Thay vì tranh luận theo sở thích, đánh giá:
- Có đáp ứng identity/security/telemetry/deployment contract không?
- Chi phí support và on-call tăng bao nhiêu?
- Rủi ro chuỗi cung ứng và patch management?
- Năng lực nhóm có đủ vận hành không?
- Có phương án golden path mở rộng hoặc adapter không?

Chọn giải pháp dựa trên trade-off đã được ghi, có người chịu trách nhiệm.

## 24. Một tình huống microservices: tự chủ hay phá hợp đồng?

Hệ thống có Order, Inventory và Notification:

~~~text
Order Service
   |
   +-- POST /inventory/reservations
   |
   +-- Event: OrderConfirmed
                |
                v
        Notification Service
~~~

Inventory Team thay đổi:

1. Đổi cách lưu reservation từ bảng SQL sang key-value store.
2. Chuyển validation thành một module Java khác.
3. Thay API từ trả reservationId sang chỉ trả boolean.
4. Thay timeout kỳ vọng từ dưới 300 ms sang chờ 10 giây.
5. Gộp lỗi OUT_OF_STOCK và TEMPORARY_FAILURE thành cùng status.
6. Thêm tracing spans và metric mới theo chuẩn tổ chức.

Phân loại:

| Thay đổi | Bản chất | Cách xử lý |
|---|---|---|
| 1. Storage nội bộ | Tự chủ nếu không thay semantics, durability và policy | Review trong team, test đầy đủ |
| 2. Refactor module | Cục bộ | Tự quyết |
| 3. Response breaking | Hợp đồng liên team | Version/migration và consumer tests |
| 4. Latency thay đổi lớn | Reliability contract | Phối hợp caller deadline/SLO |
| 5. Error semantics thay đổi | Hợp đồng nghiệp vụ | Review và migration |
| 6. Telemetry theo convention | Tương thích và hữu ích | Tự triển khai, kiểm automation |

Nếu Inventory viện cớ “database của chúng tôi, muốn đổi gì cũng được” cho 3–5, họ đang bỏ qua hợp đồng. Nếu Order phản đối 1–2 chỉ vì thích SQL và Java package cũ, Order đang vượt quá ranh giới quyết định của mình.

## 25. Tự chủ nhóm phải có cơ chế đo lường

Chỉ đo số lần deploy/ngày có thể khuyến khích chia nhỏ release nhưng không nói nhóm có thực sự độc lập hoặc an toàn không.

### 25.1. Tín hiệu về tự chủ

- Lead time từ ý tưởng đến release.
- Tỷ lệ thay đổi cục bộ không cần phối hợp release.
- Số team phải tham gia một feature thông thường.
- Số blocker kéo dài do chờ review API/platform.
- Thời gian tạo service mới bằng self-service.
- Số thao tác thủ công để deploy/rollback.
- Developer cognitive load và mức hài lòng với golden path.
- Số service có owner, runbook và SLO rõ ràng.

### 25.2. Tín hiệu về tuân thủ hợp đồng

- Breaking API/event changes bị phát hiện trước deploy.
- Consumer contract test failures.
- Số incident do schema/semantics không tương thích.
- Tỷ lệ service hỗ trợ trace context và log metadata.
- Auth/secret/data policy violations.
- Số dependency bị overload do retry/quota không tuân thủ.
- Mức độ đầy đủ ownership/DRI của public contracts.
- Số ngoại lệ hết hạn hoặc không có người chịu trách nhiệm.
- Số rollout phải rollback vì integration errors.
- Độ trễ deprecation/migration của hợp đồng cũ.

### 25.3. Cẩn thận khi dùng chỉ số

Metrics không nên trở thành bảng xếp hạng team thuần túy. Một nhóm sở hữu Payment có nhiều ràng buộc pháp lý và rủi ro hơn nhóm sở hữu giao diện nội bộ; tốc độ deploy không so sánh một-một.

Nên dùng metric để tìm **nút thắt tổ chức và chất lượng hợp đồng**, ví dụ “95% thay đổi API chờ một người duyệt vì không có automation” hoặc “số incident do event schema tăng sau khi bỏ contract tests”.

## 26. Những anti-pattern phổ biến

**“You build it, you own it” nhưng không hỗ trợ vận hành.** Team bị giao on-call mà không có observability, rollback hoặc quyền hạ tầng. Quyền sở hữu cần đi với năng lực và quyền thực tế.

**“Mỗi team một framework bất kỳ, không cần telemetry chung.”** Integration và incident trở nên đắt đỏ. Cho phép công nghệ khác nhau nhưng vẫn có interoperability và operations contract.

**“Cùng một thư viện domain cho tất cả.”** Refactor một class buộc mọi service nâng version; coupling chuyển từ API sang build-time dependency.

**“Ai là owner service thì được sửa API mà không hỏi ai.”** Service ownership không xóa quyền lợi của consumers đang phụ thuộc contract.

**“Cứ thêm field là không breaking.”** Có thể lộ dữ liệu nhạy cảm, vượt payload limit hoặc client strict parser lỗi. Cần test và đánh giá semantics.

**“Microservices nên share DB để query tiện.”** Schema ownership bị phá và migration có thể làm hỏng team khác. Chỉ dùng ngoại lệ có thời hạn khi cần.

**“Mọi quyết định phải qua architecture board.”** Team không thể tự làm thay đổi cục bộ, backlog phê duyệt tăng. Dùng guardrails và automation thay gate thủ công.

**“Không cần chuẩn chung vì team giỏi tự biết.”** Mỗi nhóm có assumptions riêng về token, timeout, retries, retention và incident; rủi ro hệ thống tăng.

**“Bắt mọi team dùng một JSON error shape là đủ.”** Error semantics, retryability, idempotency và observability cũng là contract.

**“Chỉ cần OpenAPI compile.”** Schema có thể giống nhưng cách tính tiền, thời điểm trạng thái và failure behavior đổi. Cần semantic contract tests và review.

**“Mỗi team chịu trách nhiệm SLO của mình là đủ.”** Business workflow qua nhiều service có thể thất bại dù dashboard cục bộ đạt mục tiêu.

**“Nếu người dùng khác đã subscribe event thì đó là vấn đề của họ.”** Producer cần có nghĩa vụ compatibility và deprecation theo hợp đồng.

**“Tách API version là có thể xóa ngay version cũ.”** Consumer migration, replay lịch sử và external clients có thể còn tồn tại. Cần inventory, window và telemetry.

**“Ngoại lệ là dấu hiệu governance thất bại.”** Ngoại lệ có chủ, điều kiện và review có thể hợp lý; ngoại lệ vô hạn, không được ghi nhận mới nguy hiểm.

**“Golden path bắt buộc mọi thứ, kể cả lựa chọn cục bộ.”** Platform biến thành bottleneck và team mất trách nhiệm. Chuẩn hóa ranh giới có lợi ích thật, không chuẩn hóa theo sở thích.

**“Consensus cho mọi thứ.”** Không có decision owner, mọi RFC kéo dài vô hạn. Cần scope, deadline và escalation.

## 27. Kịch bản thiết kế: 12 team cùng xây nền tảng thương mại

Giả sử một tổ chức có các nhóm:
- Identity, Customer, Catalog, Inventory, Cart, Order, Payment, Fulfillment, Notification, Analytics, Platform, Security.
- Mỗi nhóm có quyền deploy service của mình.
- API Gateway chung.
- Kafka để phát domain events.
- Customer data có thông tin cá nhân nhạy cảm.
- Payment có quota và semantics idempotency nghiêm ngặt.
- Platform cung cấp Kubernetes, telemetry và CI/CD.

Sau sáu tháng xuất hiện:
1. Hai team dùng cùng field status nhưng nghĩa khác nhau.
2. Inventory đổi event schema khiến Fulfillment DLQ tăng.
3. Một team tăng retry 5 lần và làm Payment timeout cả cụm.
4. Ba service không có trace context, incident khó xác định.
5. Catalog muốn dùng công nghệ runtime khác template.
6. Analytics subscribe mọi topic để thu raw payload.
7. Platform yêu cầu mọi PR đều chờ approval thủ công.
8. Một external API còn client dùng contract cũ nhưng team muốn xóa ngay.

### 27.1. Câu hỏi

1. Vấn đề nào là quyết định cục bộ, vấn đề nào là phá hợp đồng?
2. Nên đặt owner và cách versioning cho API/event ở đâu?
3. Cần policy gì cho retry, SLO, quota, identity và data sharing?
4. Làm thế nào để Catalog chọn runtime khác mà vẫn vận hành được?
5. Cách thay approval thủ công bằng fitness functions mà không hạ chuẩn?
6. External API migration cần lộ trình gì để không bắt mọi client cùng deploy?
7. Làm thế nào đo tổ chức vừa tự chủ vừa tránh incident liên team?

### 27.2. Định hướng giải

- Định nghĩa event/domain semantics ở ranh giới, tách bounded contexts thay vì dùng một enum status khắp nơi.
- Producer chịu trách nhiệm compatibility của event; consumer có contract tests và observability, thay đổi breaking cần migration.
- Shared quota/retry/deadline policy và per-service SLO rõ, không để một caller tự nhân tải vào Payment.
- Identity/data classification là guardrail chung; Analytics chỉ nhận fields và purposes được phép.
- Catalog có thể dùng runtime khác sau khi chứng minh compliance với build, security, telemetry và support contract, với exception nếu cần.
- Platform xây CI policies, contract checks, templates và self-service; review thủ công tập trung các ngoại lệ thực sự.
- API cũ đi qua expand → migrate → contract, có usage telemetry và thông báo.
- Đo lead time, independent deploy rate, contract-related incidents, test coverage của boundary, reliability và số ngoại lệ chưa được xử lý.

## 28. Quy trình nhẹ cho một thay đổi cục bộ

Một thay đổi thuần nội bộ có thể:

~~~text
Developer proposes implementation change
          |
          v
Team code review + automated tests
          |
          v
Contract/security/platform checks pass
          |
          v
Canary or direct rollout per risk
          |
          v
Observe SLO and rollback if needed
~~~

Không cần liên hệ tất cả team cho một index mới nếu không ảnh hưởng contract. Nhưng **chính team sở hữu service vẫn chịu trách nhiệm** khi query tối ưu sai gây lock contention lên DB chia sẻ. Local decision không đồng nghĩa không có externalities; khi phát hiện tác động chung, phải điều chỉnh ngân sách và phối hợp.

## 29. Quy trình cho thay đổi liên team

Một thay đổi public contract có thể:

~~~text
Identify affected consumers
          |
          v
Draft contract change proposal
          |
          v
Review data/security/reliability semantics
          |
          v
Agree compatibility + rollout phases
          |
          v
Add provider/consumer contract tests
          |
          v
Expand producer / deploy adapters
          |
          v
Migrate consumers, monitor usage/errors
          |
          v
Contract old version only when safe
          |
          v
Update docs/ADR/ownership
~~~

Bản đề xuất nên ngắn và có thông tin cần quyết: **what changes, why, who breaks, how to migrate, when to remove, how to rollback**.

### 29.1. Dùng deadline cho review, không cho correctness

Một thời hạn phản hồi giúp RFC không bị treo vì không ai trả lời. Nhưng hết hạn phản hồi không tự biến breaking change thành an toàn. Khi còn consumer chưa sẵn sàng, phải giữ compatibility hoặc có cơ chế điều phối/rủi ro được phê duyệt, thay vì xóa API theo lịch bất kể hậu quả.

## 30. Checklist ranh giới tự chủ và hợp đồng chung

Trước khi một team đổi service hoặc công bố service mới, xác nhận:

1. **Owner:** service, API, event, data asset và SLO có owner/DRI rõ?
2. **Domain:** bounded context và semantics được mô tả, tránh dùng shared entity tùy tiện?
3. **Scope:** thay đổi là cục bộ hay có ảnh hưởng consumer, platform, policy?
4. **API:** OpenAPI/protobuf/schema, error codes, pagination và idempotency có được công bố?
5. **Events:** event semantics, version, ordering, duplicate/replay, retention có rõ?
6. **Compatibility:** các tổ hợp old/new producer/consumer có được test theo rollout?
7. **Data:** classification, purpose, minimization, retention, deletion và quyền export được bảo vệ?
8. **Identity:** authentication, authorization, tenant isolation và secret management đáp ứng guardrails?
9. **Reliability:** SLO, timeout, deadline, retry budget, rate/concurrency limits và fallback có thỏa thuận?
10. **Observability:** trace propagation, structured logs, redaction, metrics, alerts và runbooks đủ?
11. **Deployment:** readiness, liveness, graceful shutdown, migration, canary và rollback?
12. **Ownership lifecycle:** consumer inventory, deprecation, escalation và incident coordination?
13. **Decision record:** thay đổi lớn có ADR/RFC với trade-off, owner và ngày review?
14. **Automation:** contract diff, consumer tests và policy checks chạy trong CI/CD?
15. **Exception:** nếu đi ngoài chuẩn, có điều kiện, người phê duyệt và thời hạn rõ?
16. **Capacity:** thay đổi có ảnh hưởng quota, shared DB, broker, retries hoặc failure domain?
17. **Cognitive load:** team có đủ năng lực vận hành quyết định của mình không?
18. **Feedback loop:** sau deploy có metric xác minh contract/SLO và khả năng rollback?
19. **Contract discoverability:** người dùng của API/event có tìm được docs, owner, changelog và support?
20. **Business outcome:** quyết định giúp sản phẩm nhanh hơn mà không phá tính đúng và an toàn của hệ thống?

## 31. Ghi nhớ cốt lõi

- **Tự chủ nhóm là quyền ra quyết định trong ranh giới sở hữu, đi cùng trách nhiệm về kết quả.** Nó không phải giấy phép phá API, event, security, data hoặc reliability contract.
- **Chuẩn hóa những gì cần tương thích và an toàn ở ranh giới; để tự do các chi tiết nội bộ có thể thay đổi độc lập.** Cách làm này giảm coupling mà vẫn cho phép đổi mới.
- **Hợp đồng chung phải chứa cả semantics, lỗi, timeout, retries, versioning, privacy và ownership**, không chỉ kiểu JSON.
- **Breaking change cần migration có kế hoạch**, ưu tiên expand-and-contract, contract tests và usage telemetry thay vì lockstep deployment.
- **Shared guardrails nên dễ thực thi qua golden path và CI/CD**, chỉ đưa ngoại lệ/ảnh hưởng thật tới review thủ công.
- **Platform team là người cung cấp năng lực self-service; các team nghiệp vụ vẫn sở hữu domain, service và on-call.**
- **Không có governance là hỗn loạn; quá nhiều governance là đình trệ.** Mục tiêu là quy tắc tối thiểu, rõ ràng và có thể kiểm chứng giúp toàn tổ chức thay đổi độc lập mà hệ thống vẫn ổn định.
