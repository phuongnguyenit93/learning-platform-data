# Message audit metadata

## 1. Metadata audit phải giúp giải thích một tác động nghiệp vụ

Trong hệ thống dùng message, một yêu cầu có thể đi qua API, outbox relay, broker và nhiều consumer trước khi tạo tác động cuối. Khi có sự cố, một dòng “message processed” không đủ để biết ai đã yêu cầu, nguồn nào được tin, dữ liệu của tenant nào bị thay đổi và thay đổi đã commit hay chưa.

**Message audit metadata** là tập thông tin có cấu trúc được ghi để giải thích nguồn gốc, ngữ cảnh quyền, quá trình xử lý và kết quả của message. Metadata này giúp điều tra các tình huống như:

- Một yêu cầu hoàn tiền bị xử lý nhiều lần.
- Consumer thao tác nhầm đối tượng hoặc nhầm tenant.
- Worker dùng quyền kỹ thuật rộng hơn quyền của người khởi tạo.
- Message vượt qua một bước phê duyệt.
- Một sự kiện thành công xuất hiện trong log dù transaction đã rollback.
- Một message bị phát lại nhưng không còn đủ dấu vết để xác định tác động trước đó.

Trong bảo mật logic nghiệp vụ, audit cần nối được **người khởi tạo → message → quyết định quyền → operation → tác động bền vững**. Việc có nhiều field trong log không tự tạo ra liên kết này nếu các field lấy từ nguồn không đáng tin hoặc được ghi sai thời điểm.

## 2. Phân biệt audit, metadata vận chuyển và tracing

| Loại thông tin | Mục đích chính | Giới hạn |
| --- | --- | --- |
| Metadata vận chuyển | Giao nhận, định tuyến và vận hành broker | Không tự chứng minh quyền nghiệp vụ của người gửi |
| Trace/span | Quan sát đường đi, độ trễ và lỗi kỹ thuật | Có thể thiếu đoạn hoặc bị sampling; không thay bằng chứng audit |
| Audit metadata | Giải thích chủ thể, quyền, đối tượng và kết quả | Cần cơ chế ghi bền vững và kiểm soát quyền riêng |
| Dữ liệu nghiệp vụ | Trạng thái đơn, ledger, approval, lịch sử thay đổi | Là căn cứ đối chiếu, không nên sao chép toàn bộ vào log |

Topic, queue, partition hoặc offset có thể giúp tìm message, nhưng không phải danh tính actor. Trace ID giúp nối các bước, nhưng không chứng minh actor có quyền hoàn tiền.

Một ứng dụng có thể đưa audit event qua hạ tầng logging hoặc message chung. Khi đó vẫn cần xác định độ bền, cơ chế retry, quyền đọc/ghi và khả năng đối chiếu phù hợp. Không mặc định stdout hoặc một span sampled đã đáp ứng yêu cầu lưu bằng chứng.

### 2.1. Audit không thay thế kiểm soát nghiệp vụ

Các trường `approved: true` hoặc `authorized: true` trong metadata không tự cho phép consumer bỏ kiểm tra. Cần biết quyết định do đâu tạo ra, ràng buộc với hành động và đối tượng nào, còn hiệu lực hay không.

Audit ghi lại quyết định và bằng chứng liên quan. Quyền theo đối tượng, state machine, transaction và idempotency vẫn phải được thực thi ở nơi tạo tác động.

## 3. Bắt đầu từ các câu hỏi điều tra

Trước khi chọn field, xác định những câu hỏi hệ thống phải trả lời:

1. Ai là người thực sự khởi tạo, có đang thao tác thay ai không?
2. Miền nghiệp vụ nào phát message và nguồn đó được xác minh bằng cách nào?
3. Message yêu cầu hoặc khẳng định điều gì?
4. Tenant và tài nguyên nào đã được xác minh?
5. Quyết định cho phép dựa trên policy, approval hoặc operation nào?
6. Đây là lần xử lý mới, bản sao chuyển phát hay lần retry của cùng operation?
7. Tác động nào đã commit, tác động nào chưa biết kết quả?
8. Khi có lỗi hoặc thu hồi quyền, attempt nào đã dừng và attempt nào còn tiếp tục?

Ví dụ, để điều tra “ví khách hàng tăng tiền hai lần”, chỉ có message ID chưa đủ. Cần nối đến refund request đã duyệt, operation ID, ledger entry, các attempt và cơ chế chống trùng.

### 3.1. Những bất biến của dấu vết audit

| Bất biến | Hệ quả |
| --- | --- |
| Danh tính đã xác minh không lấy từ field tự khai | Tách claimed identity khỏi verified identity |
| Một tác động truy được nguồn và operation | Giữ định danh ổn định qua relay và retry |
| Không khẳng định thành công trước khi có kết quả tương ứng | Phân biệt được nhận, được phép, đã commit và đã xác nhận ngoài hệ thống |
| Tác động nội bộ có bằng chứng bền vững đi cùng | Audit/outbox cùng transaction khi phù hợp |
| Bản sao không làm tăng số tác động được báo cáo | Phân biệt attempt, event chuyển phát và business effect |
| Audit không tự làm lộ dữ liệu nhạy cảm | Chỉ lưu thông tin cần thiết, giảm nội dung và kiểm soát truy cập |
| Dữ liệu không tin cậy không làm sai vùng phân quyền audit | Không dùng tenant tự khai để cấp quyền đọc hoặc gán trách nhiệm |

## 4. Nhóm định danh: đừng dùng một ID cho mọi mục đích

| Định danh | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `audit_event_id` | Một bản ghi audit bất biến | `audit-901` |
| `source_message_id` | Message nghiệp vụ gốc theo namespace của issuer | `command-882` |
| `transport_message_id` | ID do lớp vận chuyển cung cấp nếu có | `broker-msg-42` |
| `delivery_id` | Một lần consumer tiếp nhận delivery theo hợp đồng nội bộ | `delivery-31` |
| `attempt_id` | Một lần thử xử lý | `attempt-3` |
| `business_operation_id` | Ý định nghiệp vụ bền vững | `refund-request-781` |
| `effect_id` | Tác động đã được ghi nhận | `ledger-entry-620` |
| `correlation_id` | Nhóm công việc có liên quan | `support-case-91` |
| `causation_ref` | Tham chiếu sự kiện/lệnh trực tiếp dẫn đến bước này | Issuer và ID của message cha |
| `trace_id`, `span_id` | Liên kết quan sát kỹ thuật | ID theo hệ thống tracing đang dùng |

Tên và định dạng ID tùy hệ thống. Quan trọng là mỗi trường có một ý nghĩa nhất quán và namespace rõ.

### 4.1. Retry giữ gì, thay gì?

Khi cùng message bị giao lại:

- Giữ source message ID và operation ID.
- Tạo delivery/attempt ID mới theo cách mô hình đã định nghĩa.
- Mỗi sự kiện audit mới có audit event ID riêng.
- Nếu relay gửi lại chính một audit event, giữ audit event ID để kho nhận khử trùng.
- Không tạo effect ID mới nếu lần xử lý chỉ đọc kết quả đã có.

Một audit event được chuyển ba lần khác với ba audit event về ba attempt. Cả hai cũng khác với ba tác động nghiệp vụ.

### 4.2. Causation cần rõ loại và namespace

Một chuỗi minh họa:

~~~text
Yêu cầu API
  -> refund request được duyệt
  -> command yêu cầu ghi có vào ví
  -> audit về quyết định quyền
  -> ledger entry đã commit
  -> event thông báo kết quả
~~~

Nếu dùng một trường `parent_id` không cho biết đó là message, audit event hay operation, việc dựng lại chuỗi dễ bị nhầm. Có thể dùng tham chiếu có loại và issuer, hoặc một quy tắc namespace được thống nhất.

Correlation ID chỉ cho biết các công việc có liên quan. Nó không đủ để kết luận sự kiện nào trực tiếp gây ra tác động nào, và không được dùng làm bằng chứng phân quyền.

## 5. Danh tính và phạm vi: ghi cả giá trị lẫn căn cứ tin cậy

### 5.1. Các danh tính cần giữ riêng

| Trường khái niệm | Nội dung |
| --- | --- |
| Initiating actor | Người hoặc thành phần khởi tạo operation |
| Effective subject | Người dùng mà actor đang thao tác thay nếu có |
| Business issuer | Miền phát message có thẩm quyền theo hợp đồng |
| Transport publisher | Thành phần kết nối và publish, có thể là relay |
| Execution principal | Worker/consumer thực thi tác động |
| Approver | Người hoặc cơ chế phê duyệt khi nghiệp vụ yêu cầu |

Không ghi actor bằng `system` rồi làm mất người khởi tạo chỉ vì tác động xảy ra ở worker. Cũng không điền người dùng cuối làm execution principal khi thực tế worker mới là bên truy cập database.

Với tác vụ tự động, cần phân biệt người cấu hình với thành phần thực sự kích hoạt operation. Người tạo lịch tháng trước không nhất thiết đang chủ động thực hiện từng lần chạy hôm nay. Có thể giữ `schedule_id`, `configured_by` và danh tính tự động kích hoạt để thể hiện đúng quan hệ.

### 5.2. Danh tính tự khai, được xác nhận và được xác thực trực tiếp

Một message có `actor_id: user-42` không chứng minh user-42 đã thực hiện hành động.

Audit nên thể hiện nguồn của khẳng định, chẳng hạn:

- Actor được xác thực trực tiếp ở API đầu vào.
- Actor được producer đáng tin xác nhận theo hợp đồng truyền ngữ cảnh.
- Actor chỉ xuất hiện trong dữ liệu tự khai chưa được kiểm chứng.
- Không xác định được actor hoặc sự kiện không có actor là con người.

Consumer xác minh producer không có nghĩa consumer đã trực tiếp xác thực lại người dùng gốc. Cần giữ căn cứ và trách nhiệm của nơi đưa ra khẳng định đó.

Một mô hình có thể tách:

~~~text
claimed_issuer
verified_issuer
claimed_actor_ref
initiating_actor_ref
identity_assertion_source
identity_assurance
~~~

Không nhất thiết mọi event đều có mọi trường. Khi chưa có căn cứ, để trạng thái phù hợp như `UNVERIFIED` hoặc `UNKNOWN`, không bịa danh tính để lấp chỗ trống.

### 5.3. Tenant phải được xác minh trước khi gán trách nhiệm và quyền đọc

Tenant do payload khai báo cần được đối chiếu với nguồn, operation và tài nguyên. Một bên tấn công có thể cố ghi `tenant_id` của nạn nhân để làm nhiễu điều tra hoặc đưa dữ liệu vào không gian audit mà người khác được đọc.

Với message bị chặn trước khi xác minh tenant, có thể lưu claimed tenant trong vùng sự kiện bảo mật do hệ thống quản lý. Không tự đưa bản ghi đó vào lịch sử của tenant được khai báo như một hành động đã được xác thực.

Quyền đọc audit cũng phải dựa trên tenant đã được xác định đúng và chính sách truy cập, không chỉ dựa vào giá trị một field do producer bất kỳ gửi.

## 6. Thời gian và thứ tự phải được diễn giải đúng

| Trường minh họa | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `source_occurred_at` | Thời gian nguồn cho rằng sự kiện xảy ra | Phụ thuộc đồng hồ và khẳng định của nguồn |
| `received_at` | Consumer tiếp nhận message | Không phải thời điểm nghiệp vụ gốc xảy ra |
| `decision_at` | Thời điểm đánh giá chính sách | Không chứng minh tác động đã commit |
| `recorded_at` | Thời điểm ghi bản ghi ở nguồn audit theo hợp đồng | Nếu được tạo trong transaction, có thể sớm hơn commit |
| `ingested_at` | Kho audit tập trung nhận sự kiện | Có thể trễ do relay hoặc sự cố |
| `committed_at` nếu có | Mốc commit lấy từ cơ chế đủ tin cậy | Không tự gán từ đồng hồ ứng dụng trước commit |

Dùng cách biểu diễn múi giờ thống nhất, thường bằng UTC, và giữ đủ độ chính xác cho nhu cầu điều tra. Đồng thời phải biết đồng hồ nào đã tạo từng mốc.

Không dùng timestamp làm bằng chứng duy nhất về thứ tự tuyệt đối giữa nhiều dịch vụ. Có thể bổ sung causation, version đối tượng hoặc sequence theo một phạm vi được định nghĩa.

Offset có thể hỗ trợ thứ tự trong phạm vi luồng mà broker cam kết. Không suy ra thứ tự toàn hệ thống hoặc thứ tự commit giữa nhiều cơ sở dữ liệu từ hai offset không cùng phạm vi.

Thời gian chênh lệch cũng không tự chứng minh có tấn công: cần xét clock drift, backlog, retry và độ trễ kho audit. Ngược lại, việc chữ ký của timestamp hợp lệ không chứng minh đồng hồ nguồn đúng.

## 7. Ghi quyết định quyền và kết quả thành các sự kiện có ý nghĩa rõ

### 7.1. Quyết định cho phép chưa phải tác động thành công

| Sự kiện minh họa | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| `message.received` | Consumer đã quan sát delivery | Nguồn hợp lệ hoặc operation được phép |
| `message.validated` | Đã vượt kiểm tra nguồn/schema theo hợp đồng | Tác động nghiệp vụ đã commit |
| `message.authorized` | Một quyết định cho phép đã được đưa ra | Transaction sẽ chắc chắn thành công |
| `business.effect.committed` | Tác động nội bộ đã commit theo cơ chế ghi nhận | Hệ thống bên ngoài đã hoàn tất bước riêng |
| `message.duplicate_detected` | Lần nhận này không tạo tác động mới | Message gốc đã thành công, trừ khi có tham chiếu kết quả chứng minh |
| `message.quarantined` | Đã cách ly theo chính sách | Nghiệp vụ đã được thực hiện |
| `external.effect.unknown` | Chưa biết chắc tác động bên ngoài | Bên ngoài chưa thực hiện |
| `external.effect.confirmed` | Có xác nhận theo hợp đồng bên ngoài | Mọi bước sau đó đều đã hoàn tất |

Với duplicate, nên ghi rõ đã tìm thấy kết quả nào hoặc chỉ phát hiện một attempt đang xử lý. Đừng gộp “đang tranh chấp” và “đã hoàn tất” thành cùng một kết quả thành công.

### 7.2. Căn cứ quyết định cần truy được

Có thể ghi:

~~~text
action
resource_type và resource_id
policy_decision_id
policy_version
approval_ref nếu có
authority_mode
reason_code
resource_version_before / resource_version_after khi cần
business_operation_id
~~~

`authority_mode` có thể phân biệt kiểm tra quyền hiện tại với thực thi một operation đã được chấp nhận bền vững. Nó không phải cờ cho phép bỏ quyền; ý nghĩa phải được chính sách nghiệp vụ định nghĩa.

Mã lý do có cấu trúc như `TENANT_MISMATCH`, `APPROVAL_MISSING` hoặc `REFUND_LIMIT_EXCEEDED` giúp truy vấn tốt hơn một chuỗi lỗi tự do. Chỉ lưu thông tin chi tiết phù hợp với quyền người đọc audit.

Phiên bản chính sách giúp truy tìm căn cứ lịch sử, nhưng không tự tái dựng được toàn bộ quyết định nếu trạng thái thành viên, ownership hoặc dữ liệu đầu vào liên quan đã thay đổi. Với nghiệp vụ cần giải thích sâu, lưu tham chiếu hoặc bằng chứng quyết định tối thiểu phù hợp, không sao chép toàn bộ dữ liệu nhạy cảm.

## 8. Ví dụ audit event cho một lần ghi có hoàn tiền

Giả sử refund service đã chấp nhận yêu cầu hoàn tiền theo quy trình phê duyệt. Wallet consumer nhận command và ghi có vào ví nội bộ. Actor gốc là nhân viên hỗ trợ thao tác thay khách hàng.

Một audit event minh họa:

~~~json
{
  "audit_schema_version": 1,
  "audit_event_id": "audit-901",
  "event_type": "refund.wallet_credit.committed",
  "phase": "BUSINESS_EFFECT",
  "outcome": "COMMITTED",
  "source_service": "wallet-consumer",
  "source_occurred_at": "2026-11-22T03:10:10Z",
  "received_at": "2026-11-22T03:10:15.100Z",
  "recorded_at": "2026-11-22T03:10:15.125Z",
  "tenant_id": "tenant-a",
  "provenance": {
    "verified_issuer": "refund-service",
    "verification_method": "MESSAGE_SIGNATURE",
    "verification_key_id": "refund-sign-3",
    "source_message_id": "command-882",
    "transport_path": "refund-wallet-commands",
    "trust_policy_version": "message-trust-8"
  },
  "initiator": {
    "actor_id": "support-42",
    "effective_subject_id": "customer-91",
    "assertion_source": "refund-service",
    "assurance": "ATTESTED_BY_TRUSTED_PRODUCER"
  },
  "executor": {
    "principal_id": "wallet-worker",
    "delivery_id": "delivery-31",
    "attempt_id": "attempt-3"
  },
  "authorization": {
    "action": "REFUND_CREDIT_WALLET",
    "decision_id": "decision-72",
    "policy_version": "refund-policy-12",
    "approval_ref": "approval-55",
    "authority_mode": "ACCEPTED_OPERATION"
  },
  "business": {
    "operation_id": "refund-request-781",
    "resource_type": "wallet",
    "resource_id": "wallet-11",
    "effect_id": "ledger-entry-620",
    "amount_minor": 100000,
    "currency": "VND",
    "changed_fields": ["wallet_balance"],
    "idempotency_result": "APPLIED_NEW"
  },
  "links": {
    "correlation_id": "support-case-91",
    "causation_ref": {
      "kind": "MESSAGE",
      "issuer": "refund-service",
      "id": "command-882"
    },
    "trace_id": "trace-501"
  }
}
~~~

Các ID và mã chính sách chỉ là ví dụ. Không có yêu cầu mọi hệ thống phải dùng cấu trúc lồng như trên.

### 8.1. Những điều cần hiểu đúng trong ví dụ

- `source_service` là nguồn tạo audit event; `verified_issuer` là nguồn message nghiệp vụ. Hai giá trị có vai trò khác nhau.
- `MESSAGE_SIGNATURE` chỉ được ghi sau khi bộ xác minh thực sự thành công và ánh xạ khóa tới issuer đúng phạm vi.
- Actor được producer xác nhận theo hợp đồng, không bị trình bày như principal mà consumer trực tiếp xác thực.
- `ACCEPTED_OPERATION` chỉ hợp lệ nếu nghiệp vụ thật sự có quy tắc cho phép tiếp tục operation đã chấp nhận. Nó không thay thế kiểm tra tenant, người nhận, số tiền và trạng thái.
- `effect_id` trỏ đến ledger entry bền vững. Một retry đọc lại kết quả không tạo ledger entry mới.
- Số tiền chỉ nên lưu khi cần cho mục đích audit và quyền truy cập cho phép; không mặc định sao chép mọi giá trị nghiệp vụ vào mọi sự kiện.
- `recorded_at` có thể được tạo lúc chèn bản ghi trong transaction. Ví dụ không tự coi nó là thời điểm commit chính xác.

Event có `COMMITTED` được ghi cùng transaction với tác động và chỉ được phát/đọc qua luồng dữ liệu đã commit. Nếu transaction rollback, event này không tồn tại như một bằng chứng thành công đã commit.

### 8.2. Không sao chép nguyên metadata do producer gửi

Consumer có thể dùng một số thông tin producer cung cấp, nhưng phải giữ nguồn và mức tin cậy. Những giá trị do consumer quan sát như `received_at`, execution principal, attempt ID và kết quả transaction phải do consumer hoặc hạ tầng đáng tin xác lập.

Nếu payload gửi sẵn `outcome: COMMITTED`, consumer không được dùng nó để khẳng định tác động của chính consumer đã thành công.

Tương tự, sender không được quyết định `verification_method`, `verified_issuer`, policy decision của consumer hoặc quyền đọc audit chỉ bằng field trong message.

## 9. Tạo metadata qua ngữ cảnh tin cậy

### 9.1. Tách dữ liệu tự khai khỏi dữ liệu đã xác minh

Một luồng xử lý có thể là:

~~~mermaid
flowchart LR
    R[Raw message và transport context] --> V[Giới hạn, xác minh nguồn, kiểm tra schema]
    V --> C[Ngữ cảnh có căn cứ tin cậy]
    C --> P[Quyết định quyền và đối chiếu nghiệp vụ]
    P --> T[Transaction tạo tác động]
    T --> A[Audit outbox đã commit]
    A --> S[Kho audit có kiểm soát]
~~~

Ngữ cảnh có căn cứ tin cậy nên chứa giá trị đã được phân loại rõ: nguồn được xác minh, actor được xác nhận qua nguồn nào, tenant đã đối chiếu, định danh message và quan sát của consumer.

Không tạo một map tên `trustedMetadata` bằng cách copy toàn bộ header. Tên biến không làm đầu vào trở thành đáng tin.

### 9.2. Mã giả xây dựng metadata

~~~java
RawMessage raw = delivery.readWithinLimits();

VerifiedEnvelope verified = sourceVerifier.verify(raw, transportContext);
VerifiedSource source = verified.source();
RefundCommand command = schemas.parseVerifiedRefund(verified);

VerifiedMessageContext messageContext = contextFactory.bind(
        source,
        command,
        delivery.observedReceivedAt(),
        consumerIdentity,
        newDeliveryId(),
        newAttemptId());

AuthorizationDecision decision = policy.requireExecutable(
        messageContext, command);

AuditContext auditContext = AuditContext.fromVerifiedInputs(
        messageContext,
        decision,
        command.businessOperationReference());

// effect và outcome được bổ sung từ kết quả thực thi thực tế.
// Không lấy chúng trực tiếp từ header/payload của producer.
~~~

Đây là mã giả về ranh giới dữ liệu, không phải API của một thư viện. Việc kiểm tra quyền và trạng thái có thể cần nằm trong transaction hoặc được kiểm tra lại sát nơi tạo tác động để giữ nhất quán.

Các constructor hoặc factory nhận dữ liệu đã phân loại giúp giảm khả năng trộn field tự khai với field đã kiểm chứng. Tuy vậy, tên kiểu dữ liệu không thay thế việc triển khai bộ xác minh đúng.

### 9.3. Trace và baggage chỉ mang thông tin được cho phép

Không chuyển nguyên các field tùy ý của người gọi sang audit hoặc baggage xuyên dịch vụ. Chỉ cho phép tập trường có ý nghĩa, giới hạn độ dài và xác định rõ bên nào được tạo chúng.

Một trace ID do client gửi có thể được giữ làm ngữ cảnh quan sát theo chính sách, nhưng không được dùng để tìm actor rồi cấp quyền. Không đặt credential, nội dung thanh toán hoặc dữ liệu riêng tư vào trace/baggage chỉ để dễ debug.

Kho audit tập trung cũng phải kiểm tra nguồn ghi audit. Nếu ứng dụng bất kỳ có thể tạo một event rồi tự nhận là wallet consumer, dấu vết tập trung có thể bị giả mạo dù consumer gốc làm đúng.

## 10. Gắn metadata với transaction và kết quả bền vững

### 10.1. Khoảng hở khi ghi audit riêng sau commit

~~~text
1. Consumer ghi có vào ví.
2. Transaction commit.
3. Consumer gửi audit sang dịch vụ log.
4. Tiến trình dừng trước khi audit được lưu bền vững.
~~~

Ví đã thay đổi nhưng bằng chứng bị thiếu. Nếu gửi audit “thành công” trước commit, transaction lại có thể rollback và để lại kết luận sai.

Với tác động nội bộ trong cùng database, có thể ghi ledger, kết quả chống trùng và audit/outbox cùng transaction:

~~~text
BEGIN
  Claim message/operation theo cơ chế chống trùng.
  Kiểm tra tenant, quyền, approval và bất biến.
  Nếu tác động đã tồn tại:
    Ghi sự kiện duplicate tham chiếu effect cũ nếu chính sách yêu cầu.
  Nếu tác động chưa tồn tại:
    Tạo ledger entry và cập nhật dữ liệu nghiệp vụ.
    Ghi kết quả thực hiện.
    Ghi audit/outbox về tác động này.
COMMIT
Sau commit, xử lý ACK theo giao thức broker.
~~~

Nếu ghi bằng chứng bắt buộc thất bại, không cho thay đổi nhạy cảm commit. Việc kho audit tập trung tạm thời không nhận được chưa nhất thiết chặn nghiệp vụ, nếu outbox bền vững vẫn hoạt động trong các giới hạn đã định nghĩa.

Cần theo dõi dung lượng, backlog và thời hạn lưu của outbox. Không để outbox đầy rồi âm thầm bỏ audit để tiếp tục các tác động bắt buộc phải có bằng chứng.

### 10.2. Relay có thể chuyển lại cùng audit event

Nếu kho audit đã lưu event nhưng xác nhận bị mất, relay có thể gửi lại. Kho nhận cần khử trùng theo namespace và audit event ID.

Không dùng source message ID để khử trùng tất cả audit event: một message có thể có sự kiện nhận, quyết định quyền, nhiều attempt và một kết quả nghiệp vụ. Gộp chúng theo message ID sẽ làm mất lịch sử hợp lệ.

Nếu cùng audit event ID xuất hiện với nội dung khác, cần chặn hoặc báo xung đột. Không âm thầm ghi đè bằng bản đến sau.

### 10.3. Audit bản sao phải tham chiếu tác động cũ

Ví dụ một command đã tạo `ledger-entry-620`, rồi được giao lại. Event mới có thể là:

~~~json
{
  "audit_event_id": "audit-902",
  "event_type": "message.duplicate_detected",
  "phase": "CONSUMPTION",
  "outcome": "ALREADY_APPLIED",
  "source_message_id": "command-882",
  "business_operation_id": "refund-request-781",
  "attempt_id": "attempt-4",
  "effect_id": "ledger-entry-620"
}
~~~

Đây là trích đoạn metadata, không phải schema đầy đủ. Nó cho biết attempt mới tham chiếu tác động đã có, không khẳng định có lần ghi có mới.

Nếu chỉ phát hiện một operation đang xử lý, dùng kết quả như `IN_PROGRESS` theo hợp đồng, không ghi `ALREADY_APPLIED` khi chưa có bằng chứng hoàn tất.

### 10.4. Từ chối và rollback cần đường ghi riêng

Một sự kiện `APPROVAL_MISSING` chèn vào cùng transaction rồi rollback cũng sẽ biến mất. Nếu cần lưu các lần bị từ chối, dùng đường ghi độc lập sau khi transaction kết thúc hoặc kênh bảo mật có độ bền phù hợp.

Lỗi ghi audit không được biến một request bị cấm thành được phép. Đồng thời cần báo tình trạng thiếu khả năng ghi nhận thay vì giả vờ mọi lần thử đều được lưu đủ.

Tiến trình có thể chết trước khi ghi kết quả lỗi. Với nghiệp vụ cần chứng minh cả việc đã nhận yêu cầu, có thể ghi một sự kiện tiếp nhận bền vững trước khi xử lý rồi đối chiếu các trường hợp chưa có kết quả.

Một bản ghi tiếp nhận không có kết quả cuối chỉ chứng minh dấu vết đang thiếu hoặc operation chưa kết thúc theo dữ liệu đang có. Nó không đủ để tự kết luận rollback, thất bại hay chưa tạo tác động.

### 10.5. ACK không nguyên tử với transaction database thông thường

Sau commit, consumer có thể chết trước ACK và nhận lại message. Audit về effect phải vẫn tồn tại; attempt mới phải được liên kết với kết quả cũ.

Một dòng `ack.attempted` chỉ ghi việc đã thử gửi ACK. Nếu giao thức/hạ tầng không cung cấp xác nhận đủ căn cứ, không đổi nó thành khẳng định chắc chắn broker đã ghi nhận ACK.

Trạng thái delivery và kết quả nghiệp vụ là hai lớp riêng. Việc message còn được giao lại không chứng minh ledger chưa commit.

### 10.6. Tác động bên ngoài cần kết quả riêng

Database nội bộ không làm một lời gọi hoàn tiền ngoài hệ thống trở nên nguyên tử với audit. Khi timeout, ghi trạng thái chưa xác định và tham chiếu operation/key để đối chiếu.

Chỉ ghi `external.effect.confirmed` khi có bằng chứng đủ tin cậy theo hợp đồng. Không gán “thất bại” chỉ vì không nhận được response rồi tạo một yêu cầu mới có thể gây tác động trùng.

## 11. Giảm dữ liệu và bảo vệ chính kho audit

### 11.1. Metadata vẫn có thể là dữ liệu nhạy cảm

ID người dùng, tài nguyên, tenant, số tiền, địa chỉ mạng và quan hệ actor–subject đều có thể tiết lộ thông tin. Chỉ lưu những gì phục vụ truy vết và kiểm chứng nghiệp vụ.

Không ghi mặc định:

- Password, OTP, access token, refresh token, cookie hoặc khóa ký.
- Toàn bộ header hoặc request/response body.
- Dữ liệu thẻ, tài khoản thanh toán đầy đủ hoặc giấy tờ cá nhân.
- Nội dung báo cáo, tin nhắn riêng tư hoặc trường bí mật chỉ vì chúng có trong payload.

Ưu tiên tham chiếu nội bộ, mã lý do, danh sách trường thay đổi và giá trị được giảm chi tiết. Nếu cần lịch sử giá trị trước/sau, có thể tách vùng lưu được bảo vệ với quyền đọc riêng.

Hash không tự biến dữ liệu thành vô danh. Giá trị có miền nhỏ có thể bị đoán và tính lại hash. Một digest của payload cũng không cho phép phục hồi nội dung phục vụ điều tra; cần xác định rõ đang cần so sánh hay cần lưu bằng chứng nội dung.

### 11.2. Chống chèn dữ liệu vào log và trang audit

Dùng sự kiện có cấu trúc, giới hạn độ dài và mã hóa đúng ngữ cảnh hiển thị. Không nối trực tiếp user agent, reason hoặc ID tự khai vào dòng log theo cách cho phép tạo dòng giả.

Trang audit phải hiển thị dữ liệu không tin cậy an toàn. Một chuỗi HTML trong metadata không được thực thi chỉ vì nó nằm trong “log nội bộ”.

Các trường được lập chỉ mục cũng cần kiểm soát độ dài và cardinality. Một producer không được làm cạn tài nguyên kho audit bằng hàng triệu tên field hoặc giá trị không giới hạn.

### 11.3. Quyền đọc, ghi, sửa và xuất dữ liệu

- Ứng dụng chỉ có quyền ghi qua đường được cấp; không tự sửa/xóa lịch sử tùy ý.
- Người dùng chỉ xem audit trong phạm vi được phép, kể cả khi biết ID bản ghi.
- Quyền xuất số lượng lớn hoặc đọc dữ liệu nhạy cảm có thể cần tách riêng.
- Nhân viên hỗ trợ không tự xóa dấu vết thao tác của mình.
- Thay đổi quyền quản trị và các truy vấn/xuất nhạy cảm được ghi nhận theo chính sách.

Append-only cần được thực thi ở lớp lưu trữ và vận hành. Tên bảng `immutable_audit` hoặc một flag trong ứng dụng không tự ngăn người có quyền quản trị sửa dữ liệu.

Hash, chữ ký hoặc checkpoint độc lập có thể hỗ trợ phát hiện sửa đổi theo mô hình đe dọa. Chúng không tự chứng minh nội dung do ứng dụng phát ra là sự thật nếu nguồn tạo audit đã bị chiếm quyền.

### 11.4. Thời hạn lưu và schema evolution

Thời hạn giữ audit cần phù hợp với nhu cầu điều tra, vận hành và yêu cầu áp dụng. Không mặc định lưu vô hạn hoặc xóa theo cùng TTL ngắn của trace.

Version schema audit tách khỏi version schema message. Khi thay nghĩa một field, cần version hoặc cơ chế tương thích rõ; không đổi `message_id` từ ID nghiệp vụ sang ID broker mà vẫn dùng cùng tên và cách đọc cũ.

Khi lưu trữ lạnh hoặc giảm dữ liệu, giữ khả năng nối operation với effect và nguồn trong phạm vi cần thiết. Kiểm tra backup/restore của kho audit, không chỉ kiểm tra dữ liệu ở hệ thống đang chạy.

## 12. Ví dụ điều tra: hoàn tiền có ba attempt nhưng một tác động

Giả sử operation `refund-request-781` đã được duyệt để ghi có 100.000 VND vào ví khách hàng.

| Bước | Sự kiện thực tế | Metadata cần liên kết |
| --- | --- | --- |
| 1 | Refund service phát command hợp lệ | Issuer, source message ID, operation, actor và approval reference |
| 2 | Wallet consumer tiếp nhận | Delivery ID, attempt ID, received time và execution principal |
| 3 | Attempt đầu gặp lỗi tạm thời trước khi commit | Kết quả retryable nếu ghi được, không có effect thành công |
| 4 | Attempt tiếp theo commit ledger và audit/outbox | Effect ID, operation, source message, quyết định quyền và outcome |
| 5 | Worker chết trước ACK | Không được suy ra rollback từ việc thiếu ACK |
| 6 | Attempt mới nhận lại command | Attempt mới nhưng cùng source message và operation |
| 7 | Consumer tìm thấy ledger đã có | Audit duplicate tham chiếu effect cũ, không ghi có thêm |
| 8 | Relay chuyển lại một audit event do mất xác nhận | Giữ audit event ID, kho nhận khử trùng bản chuyển phát |

Kết quả điều tra đúng phải chỉ ra:

- Một operation đã được chấp nhận.
- Ba attempt xử lý, với các quan sát riêng.
- Một effect ghi có thực sự.
- Một audit event cho tác động, có thể được chuyển nhiều lần.
- Actor khởi tạo, subject được hỗ trợ và worker thực thi có vai trò khác nhau.

Đếm số attempt “thành công” hoặc số dòng có từ “processed” sẽ dễ tạo kết luận sai. Đếm số tiền từ mọi bản sao audit cũng có thể làm báo cáo tăng gấp đôi.

### 12.1. Nếu payload tự khai người phê duyệt

Giả sử message gửi `approvedBy: lead-12` nhưng server không tìm thấy approval phù hợp với operation và nội dung hiện tại.

Audit cần cho thấy yêu cầu bị từ chối vì thiếu căn cứ phê duyệt. Giá trị lead-12, nếu cần giữ phục vụ điều tra, phải được phân loại là giá trị tự khai, không ghi như người thực sự đã duyệt.

Không ghi `APPROVED` chỉ vì producer đưa một chuỗi giống ID nhân viên. Định danh approval phải được ràng buộc với nguồn, operation và nội dung cần duyệt theo hợp đồng.

### 12.2. Đối chiếu tác động với bằng chứng audit

Một truy vấn minh họa trên dữ liệu đã chuẩn hóa:

~~~sql
SELECT
    e.tenant_id,
    e.operation_id,
    e.ledger_entry_id
FROM wallet_refund_effect e
LEFT JOIN audit_projection a
    ON  a.tenant_id = e.tenant_id
    AND a.business_operation_id = e.operation_id
    AND a.effect_id = e.ledger_entry_id
    AND a.event_type = 'refund.wallet_credit.committed'
    AND a.outcome = 'COMMITTED'
WHERE e.execution_mode = 'MESSAGE'
  AND e.created_at < :cutoff_time
  AND a.audit_event_id IS NULL;
~~~

Tên bảng và placeholder chỉ minh họa ý tưởng. `cutoff_time` cần chừa khoảng độ trễ chuyển phát được chấp nhận nếu audit projection nằm ở kho tập trung.

Một kết quả thiếu audit là tín hiệu đối chiếu, không tự là bằng chứng tiền chưa được ghi có. Cần tìm bản ghi nguồn, outbox, tình trạng relay và lỗi projection.

Dữ liệu hiệu ứng dùng để đối chiếu phải bao phủ các đường ghi liên quan. Nếu một đường ghi trái phép có thể bỏ qua cả ledger cần kiểm tra lẫn audit, việc nối hai bảng này không chứng minh mọi thay đổi đều được theo dõi.

### 12.3. Các câu hỏi để khoanh vùng nhanh

Khi có báo cáo bất thường, có thể lần theo thứ tự:

1. Xác định tenant và effect/operation từ nguồn nghiệp vụ đáng tin.
2. Tìm audit về tác động đã commit và kiểm tra căn cứ nguồn.
3. Liên kết source message với toàn bộ delivery/attempt.
4. Kiểm tra actor, subject, approval và quyết định quyền.
5. So sánh nội dung có bị xung đột dưới cùng ID không.
6. Kiểm tra bản sao chuyển phát, độ trễ và các trạng thái chưa xác định.
7. Đối chiếu dữ liệu cuối, không sửa lịch sử để che chênh lệch.

## 13. Kiểm thử message audit metadata

Kiểm thử metadata cần đi cùng tác động nghiệp vụ. Chỉ kiểm tra logger đã được gọi không chứng minh dấu vết bền vững hoặc nội dung đúng.

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Producer tự đặt actor/issuer không có căn cứ | Không xuất hiện như danh tính đã xác minh |
| Nguồn hợp lệ xác nhận actor theo hợp đồng | Audit giữ đúng assertion source và mức căn cứ |
| Message thiếu actor con người | Không tự bịa một người; vẫn giữ nguồn và execution principal |
| Message khởi tạo trong impersonation | Giữ riêng actor thật và effective subject |
| Job chạy theo lịch | Phân biệt người cấu hình, nguồn kích hoạt và worker |
| Tenant trong payload bị thay | Không gán sai tenant đã xác minh hoặc quyền đọc audit |
| Relay chuyển message | Không làm mất issuer gốc hay nhầm relay là người đưa ra quyết định nghiệp vụ |
| Cùng message được giao lại | Giữ source ID/operation; có attempt mới |
| Cùng audit event được chuyển lại | Khử trùng theo audit event ID trong namespace đúng |
| Cùng audit event ID nhưng nội dung khác | Phát hiện xung đột, không ghi đè âm thầm |
| Cùng operation xuất hiện dưới message ID khác | Tác động vẫn được chống trùng, audit liên kết về operation/effect |
| Hai worker xử lý đồng thời | Một tác động hợp lệ, các attempt có thể được phân biệt |
| Message vượt quyền hoặc thiếu approval | Không có effect thành công, có kết quả từ chối theo chính sách |
| Transaction rollback sau khi tạo dữ liệu tạm | Không tồn tại audit thành công đã commit cho thay đổi bị rollback |
| Ghi audit/outbox bắt buộc thất bại | Tác động nhạy cảm không commit một mình |
| Worker chết sau commit trước ACK | Effect và audit còn bền vững; retry tham chiếu kết quả cũ |
| ACK không có xác nhận đủ căn cứ | Không khẳng định chắc broker đã ghi nhận chỉ từ dòng log gửi ACK |
| Timeout với hệ thống ngoài | Audit thể hiện chưa xác định, không tự gán thất bại hoặc thành công |
| Mất trace/span do sampling | Vẫn nối được operation và effect bằng audit bền vững |
| Đồng hồ nguồn lệch hoặc event đến trễ | Không suy ra thứ tự sai chỉ từ timestamp |
| Kho audit tập trung ngừng tạm thời | Outbox giữ bằng chứng và relay tiếp tục theo giới hạn vận hành |
| Lỗi schema projection | Không mất âm thầm dữ liệu; có cơ chế cách ly/đối chiếu |
| Metadata chứa token hoặc payload nhạy cảm | Quy tắc giảm dữ liệu ngăn lưu không cần thiết |
| Chuỗi chứa xuống dòng/HTML | Không giả mạo dòng log hoặc thực thi trong trang audit |
| Người dùng biết audit ID của tenant khác | Không đọc/xuất được bản ghi ngoài quyền |
| Ứng dụng khác tự nhận là nguồn audit | Đường ghi tập trung không chấp nhận danh tính tự khai |
| Restore hoặc lưu trữ lạnh | Vẫn giải thích được liên kết nguồn–operation–effect trong phạm vi lưu cần thiết |

Với lỗi transaction, kiểm tra dữ liệu đã commit từ kết nối độc lập. Đọc một object vừa tạo trong chính transaction của test không đủ chứng minh nó bền vững.

Với race condition, dùng điểm đồng bộ để tạo các attempt tranh chấp thật. Với thời gian, dùng đồng hồ điều khiển được để kiểm tra các mốc lệch, nhận trễ và ghi trễ.

Với giảm dữ liệu, kiểm tra bản ghi thực tế trong audit/outbox và kho nhận. Một serializer phụ hoặc logger bắt exception có thể vô tình ghi nguyên message dù business audit event đã được thiết kế gọn.

Với quyền đọc, kiểm tra cả truy vấn, trang chi tiết và chức năng export. Bảo vệ giao diện chính chưa đủ nếu API tải báo cáo audit vẫn cho chọn tenant tùy ý.

## 14. Tiêu chí hoàn thành thiết kế metadata

Một thiết kế cần có câu trả lời cụ thể cho các điểm sau:

- Mỗi ID thuộc về message, delivery, attempt, operation hay effect?
- Trường danh tính và tenant lấy từ đâu, được xác minh đến mức nào?
- Producer, relay, người khởi tạo và consumer có được phân biệt không?
- Mỗi mốc thời gian phản ánh quan sát nào, có thể dùng để kết luận điều gì?
- Quyết định quyền có truy được policy, approval và phạm vi đối tượng không?
- Kết quả có phân biệt đã nhận, được phép, đã commit, duplicate và chưa xác định không?
- Bằng chứng bắt buộc có bền vững cùng tác động nội bộ không?
- Retry và chuyển phát lại có giữ định danh mà không nhân bản số tác động không?
- Audit có được giảm dữ liệu, phân quyền đọc/ghi và bảo vệ khỏi sửa đổi theo mô hình đe dọa không?
- Có cơ chế đối chiếu tác động thiếu audit và audit không khớp dữ liệu nghiệp vụ không?

Metadata hữu ích phải giúp người điều tra nối được một tác động với đúng nguồn, chủ thể và quyết định đã dẫn đến nó. Độ tin cậy của dấu vết nằm ở căn cứ của từng trường và thời điểm ghi nhận, cùng các bất biến mà hệ thống vẫn giữ khi message bị sửa, giao lại hoặc xử lý lỗi.
