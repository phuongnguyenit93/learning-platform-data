# Sensitive telemetry handling: xử lý dữ liệu nhạy cảm trong telemetry

## 1. Telemetry cũng là một đường đi của dữ liệu nghiệp vụ

Trong chương **Observability**, *sensitive telemetry handling* là cách nhận diện, giới hạn, bảo vệ và quản lý dữ liệu nhạy cảm xuất hiện trong log, metric, trace và audit event. Mục tiêu là điều tra được hành vi bỏ qua phê duyệt, sửa giá, thao tác sai quyền hoặc gửi yêu cầu trùng mà không tạo thêm một kho dữ liệu dễ bị lộ hoặc lạm dụng.

Một API hoàn tiền có thể chặn đúng yêu cầu của người dùng không có quyền. Tuy nhiên, nếu interceptor ghi toàn bộ request, hệ thống vẫn có thể làm lộ token đăng nhập, thông tin tài khoản nhận tiền, idempotency key và định danh đơn hàng vào log. Người chỉ được xem dashboard vận hành có thể tiếp cận dữ liệu mà chính API không cho họ đọc.

Bất biến cần giữ là:

> Thông tin đủ để quan sát và giải thích quyết định nghiệp vụ phải được thu thập theo phạm vi đã xác định; telemetry không được mở đường truy cập vòng qua quyền trên đối tượng, tenant hoặc dữ liệu bí mật.

Một quyết định từ chối không làm request trở nên an toàn để ghi nguyên vẹn. Kẻ tấn công có thể cố ý gửi bí mật, dữ liệu cá nhân, chuỗi rất dài hoặc ký tự điều khiển vào request bị chặn để đưa chúng vào hệ thống log.

## 2. Phân biệt các loại tín hiệu và mục đích sử dụng

Không phải mọi loại telemetry đều cần cùng mức chi tiết hoặc cùng cơ chế lưu giữ.

| Loại tín hiệu | Câu hỏi chính | Dữ liệu nên ưu tiên |
|---|---|---|
| Metric | Tần suất, tỷ lệ, độ trễ có thay đổi không? | Counter/histogram tổng hợp, nhãn hữu hạn |
| Log chẩn đoán | Một lần thực thi đã đi theo nhánh nào? | Mã sự kiện, reason code, tham chiếu liên kết đã kiểm soát |
| Trace | Thời gian và quan hệ giữa các bước ở đâu? | Tên thao tác, trạng thái, thời lượng, thuộc tính đã chọn |
| Audit event | Ai thực hiện hành động nào, theo quyết định nào, tác động gì? | Sự kiện có schema, nguồn phát đáng tin cậy, định danh và bằng chứng cần thiết trong kho hạn chế |

Metric không cần chứa email để đếm số lần `ownership_mismatch`. Trace không cần chứa request body để chỉ ra evaluator mất 300 ms vì kho trạng thái chậm. Audit có thể cần thông tin chi tiết hơn để giải thích một thay đổi giá, nhưng thông tin đó không vì vậy được sao chép vào dashboard phổ thông.

Cần phân biệt thêm hai loại sự kiện:

- **Quyết định kiểm tra:** rule đã cho phép, từ chối hoặc không đánh giá được tại một thời điểm.
- **Tác động nghiệp vụ:** transaction đã commit một khoản hoàn tiền hoặc một thay đổi trạng thái cụ thể.

Log `decision=allow` không chứng minh tác động đã commit. Phân tách ý nghĩa giúp vừa giảm dữ liệu không cần thiết, vừa tránh điều tra sai từ một bản ghi thiếu ngữ cảnh.

## 3. Phân loại dữ liệu trước khi thu thập

### 3.1. Không chỉ có mật khẩu mới nhạy cảm

Dữ liệu nhạy cảm trong module bảo vệ logic nghiệp vụ có thể thuộc các nhóm sau:

| Nhóm | Ví dụ | Cách xử lý mặc định trong telemetry thông thường |
|---|---|---|
| Bí mật truy cập | Mật khẩu, access token, refresh token, session cookie, API key | Không thu thập; không ghi cả giá trị đã mã hóa chỉ để debug |
| Mã có khả năng cấp quyền | Liên kết đặt lại mật khẩu, mã xác nhận, URL ký sẵn | Không ghi giá trị hoặc URL đầy đủ |
| Dữ liệu định danh | Email, số điện thoại, địa chỉ, user ID nội bộ | Chỉ thu thập khi có mục đích rõ; ưu tiên tham chiếu hạn chế liên kết |
| Dữ liệu giao dịch | Số tài khoản, chi tiết thanh toán, nội dung đơn hàng | Không đưa nguyên vẹn vào log/trace thông thường; audit chuyên biệt có schema riêng nếu cần |
| Thông tin thương mại | Giá gốc, biên lợi nhuận, mức chiết khấu, điều kiện đối tác | Chọn trường tối thiểu; hạn chế quyền truy cập |
| Chi tiết phòng chống lạm dụng | Ngưỡng rủi ro, công thức chấm điểm, ngoại lệ phê duyệt | Dùng mã quyết định trong telemetry phổ thông; chi tiết ở kênh điều tra phù hợp |
| Định danh liên kết | Order ID, correlation ID, trace ID, idempotency key | Đánh giá khả năng liên kết và cardinality; không mặc định là dữ liệu vô hại |

Một idempotency key do client gửi có thể chứa email hoặc thông tin đơn hàng. Không được coi mọi key là chuỗi ngẫu nhiên an toàn. Nếu cần nối các lần thử, tạo một tham chiếu thao tác do máy chủ quản lý hoặc một dấu tham chiếu có phạm vi rõ ràng; không ghi nguyên key.

### 3.2. Tổ hợp trường có thể nhạy cảm hơn từng trường

Timestamp chính xác, tenant, loại thao tác và giá trị giao dịch có thể đủ để liên kết một sự kiện với một cá nhân hoặc khách hàng cụ thể. Pseudonym của actor vẫn có thể cho phép theo dõi hành vi dài hạn.

Do đó, “không có tên hoặc email” chưa đồng nghĩa dữ liệu đã vô danh. Cần xem xét cả khả năng liên kết giữa log, trace, hệ thống hỗ trợ khách hàng và dữ liệu nghiệp vụ.

Đối với quyết định nhạy cảm, chỉ công khai reason chi tiết cho người có nhu cầu điều tra. Thông báo API cho người dùng không có quyền không nên tiết lộ đơn của người khác đã được phê duyệt hay còn hạn mức bao nhiêu.

## 4. Giảm dữ liệu tại nguồn bằng schema cho phép

### 4.1. Chọn trường được ghi thay vì cố xóa mọi trường nguy hiểm

Cách dễ gây lộ lọt:

```java
log.info("refund request={}", request);
log.warn("rule failed payload={}", objectMapper.writeValueAsString(command));
```

Một DTO hôm nay chỉ có ID và số tiền, ngày mai có thể được thêm số tài khoản hoặc token đối tác. Serialize toàn bộ đối tượng làm những trường mới tự chảy vào log mà không có quyết định thu thập riêng.

Thiết kế an toàn hơn là một schema có các trường được chọn rõ ràng:

```json
{
  "event": "business_rule_decision",
  "schema_version": 1,
  "event_id": "evt-generated-by-server",
  "occurred_at": "2026-11-22T02:00:00Z",
  "correlation_ref": "corr-generated-by-server",
  "tenant_ref": "h2.tenant-reference",
  "actor_ref": "h2.actor-reference",
  "object_type": "refund_request",
  "object_ref": "h2.object-reference",
  "operation": "refund",
  "rule": "refund_approval_required",
  "decision": "deny",
  "reason": "approval_missing",
  "rule_revision": "approval-policy-3",
  "entrypoint": "api"
}
```

Các giá trị tham chiếu trên chỉ minh họa hình thức, không phải token thực hoặc định dạng bắt buộc. Timestamp do máy chủ tạo; rule, reason, operation và entrypoint thuộc tập được quản lý. Tham chiếu tenant, actor và đối tượng được tạo từ ngữ cảnh đã xác minh, không lấy theo một field tùy ý trong request.

Schema này không chứa request body, header xác thực, giá trị idempotency key, nội dung exception hoặc công thức rủi ro. Nếu điều tra cần thêm dữ liệu, phải xác định trường, nơi lưu, quyền đọc và thời gian giữ cụ thể.

### 4.2. Các ranh giới schema cần bảo vệ

- Chỉ chấp nhận field được khai báo, giới hạn kiểu, độ dài và tập giá trị.
- Không có field tùy ý như `extra`, `metadata` hoặc `context` cho phép nhét nguyên request vào phía sau schema.
- Chuẩn hóa enum và reference bằng thành phần dùng chung; không để mỗi controller tự quyết định.
- Trường không hợp lệ phải bị từ chối hoặc loại bỏ theo hợp đồng; không ghi nguyên sự kiện lỗi vào log phụ để “debug schema”.
- Nếu cần khu vực cách ly sự kiện lỗi, chỉ giữ dữ liệu đã được xử lý an toàn hoặc metadata về lỗi; không biến nó thành kho chứa payload thô.

Bộ lọc ở collector là lớp bảo vệ bổ sung. Nó không xóa được dữ liệu đã xuất hiện ở stdout, file cục bộ hoặc queue trước collector. Giảm dữ liệu phải bắt đầu trước lần ghi đầu tiên.

## 5. Chọn đúng kỹ thuật bảo vệ từng loại dữ liệu

### 5.1. Loại bỏ, che, giả danh và mã hóa có mục tiêu khác nhau

| Kỹ thuật | Phù hợp khi | Giới hạn |
|---|---|---|
| Không thu thập | Giá trị không cần cho mục đích quan sát | Không hỗ trợ điều tra bằng chính giá trị đó; cần chọn tín hiệu khác |
| Redaction | Cần giữ cấu trúc nhưng bỏ hoàn toàn giá trị nhạy cảm | Bộ lọc theo tên trường có thể bỏ sót alias hoặc trường lồng nhau |
| Masking | Cần một phần hiển thị trong kênh có quyền phù hợp | Phần còn lại vẫn có thể nhận diện hoặc liên kết |
| Pseudonym bằng HMAC | Cần nối sự kiện theo định danh trong phạm vi xác định | Vẫn có khả năng liên kết; phải bảo vệ khóa và quyền đọc |
| Mã hóa | Cần bảo vệ dữ liệu khi truyền hoặc lưu | Người có quyền giải mã vẫn đọc được; không thay thế giảm dữ liệu |

Ví dụ, che email thành `p***@example.test` vẫn lộ domain và có thể đủ để nhận ra một người trong tenant nhỏ. Giữ bốn số cuối tài khoản cũng không tự làm log trở thành dữ liệu công khai.

Không hash mật khẩu hoặc token rồi ghi vào log để chứng minh rằng đã che. Với bí mật không cần cho telemetry, cách phù hợp là không thu thập. Những dấu giá trị ổn định còn có thể trở thành công cụ đối chiếu ngoài dự kiến.

### 5.2. HMAC cho tham chiếu định danh có phạm vi

Hash trực tiếp email hoặc số điện thoại thường không đủ để hạn chế dò đoán vì không gian giá trị có thể đoán được. Khi có nhu cầu liên kết hợp lệ, có thể tạo tham chiếu bằng HMAC với khóa bí mật:

```text
reference = HMAC-SHA256(
  secretKey,
  encodeLengthPrefixed(
    "telemetry-reference-v2",
    tenantId,
    objectKind,
    canonicalIdentifier
  )
)
```

Phần domain, tenant và loại đối tượng giúp tránh vô tình dùng cùng dấu tham chiếu cho nhiều mục đích hoặc tenant. Mã hóa có độ dài trường rõ ràng tránh hai bộ giá trị khác nhau tạo cùng thông điệp do nối chuỗi mơ hồ.

Các yêu cầu đi kèm:

1. Khóa lấy từ hệ thống quản lý bí mật; không hardcode hoặc ghi vào log.
2. Định nghĩa canonicalization phù hợp từng loại ID; không tự ý đổi hoa/thường nếu định danh có phân biệt.
3. Dùng đầu ra đủ dài; không cắt ngắn thành vài ký tự dễ va chạm.
4. Quản lý phiên bản khóa và thời gian liên kết mong muốn; rotation có thể làm một chủ thể có reference khác trước.
5. Không gọi reference là dữ liệu vô danh. Nó vẫn cần kiểm soát quyền và lưu giữ.
6. Nếu khóa bị lộ, định danh dễ đoán có thể bị dò lại; việc bảo vệ khóa là một phần của thiết kế.

Một dịch vụ cần giải quyết lại reference về đối tượng, nếu có, phải có phân quyền và audit riêng. Không cung cấp một API tra cứu tự do cho mọi người xem log.

Nếu tạo reference thất bại, không fallback sang ghi ID thô. Với telemetry tùy chọn, có thể bỏ sự kiện hoặc field theo hợp đồng; với audit bắt buộc, xử lý lỗi phải theo chính sách nghiệp vụ đã xác định.

## 6. Các điểm rò rỉ thường bị bỏ sót

### 6.1. Log HTTP ở gateway và ứng dụng

Ngay cả khi service không ghi body, proxy, gateway hoặc access logger vẫn có thể ghi URL chứa query string. Một URL kiểu `/reset?token=...` hoặc `/orders?email=...` tạo rủi ro trước khi handler nghiệp vụ được gọi.

Ưu tiên route template như `/orders/{orderId}` cho tên thao tác và trường route. Không thu thập query string, cookie hoặc header xác thực theo mặc định. Danh sách loại bỏ phải bao phủ cả logger framework, middleware, HTTP client và các chế độ debug của chúng.

Thông tin như `User-Agent`, địa chỉ IP và header do client gửi cũng có thể phục vụ nhận diện, liên kết hoặc gây tăng kích thước dữ liệu. Nếu cần cho phát hiện lạm dụng, chọn cách biểu diễn, giới hạn và kênh lưu phù hợp thay vì ghi mọi header.

### 6.2. Exception và thông điệp lỗi dependency

Exception có thể mang SQL đã gắn giá trị, connection string, URL ký sẵn hoặc response body từ đối tác. Lệnh `log.error("failed", ex)` thường in cả message và chuỗi nguyên nhân; việc không log request trực tiếp chưa loại bỏ đường lộ này.

Một bản ghi chẩn đoán phổ thông có thể chỉ giữ:

```text
event=rule_evaluation_failed
rule=refund_approval_required
error_code=dependency_unavailable
correlation_ref=corr-generated-by-server
```

Nếu cần stack trace, dùng kênh và bộ làm sạch có kiểm soát, tránh ghi biến cục bộ, payload hoặc nguyên message nhạy cảm. Không tạo fallback “serializer lỗi thì in toàn bộ object và exception”.

### 6.3. Trace, span attribute và baggage

Auto-instrumentation có thể thu thập URL, câu lệnh truy vấn, header hoặc thông tin lời gọi từ xa trước khi mã nghiệp vụ tạo span riêng. Cần cấu hình ở đúng nguồn phát, không chỉ sửa những span tự viết.

Một span đủ để điều tra bước kiểm tra có thể chứa:

```text
span_name: refund.evaluate_approval
operation: refund
rule: refund_approval_required
decision: deny
reason: approval_missing
```

Không đưa request body, số tài khoản hoặc giá trị token vào span name, attribute hay event của span. Không truyền dữ liệu nhạy cảm qua baggage: dữ liệu ngữ cảnh có thể được lan sang nhiều dịch vụ hoặc lời gọi ra bên ngoài.

Trace context từ request là dữ liệu không tin cậy. Kiểm tra định dạng và độ dài khi tiếp nhận, đồng thời phân biệt nó với reference do máy chủ quản lý. Nó không chứng minh quyền truy cập, nguồn danh tính hoặc sự đúng đắn của một sự kiện audit. Không cho client tùy ý bật ghi chi tiết chỉ bằng một header debug hoặc cờ sampling.

### 6.4. Metric và exemplar

Metric nên dùng nhãn hữu hạn như rule, operation, entrypoint, decision và reason. Không thêm actor reference, order reference hoặc trace ID vào nhãn, dù các giá trị đó đã được giả danh.

Ví dụ phù hợp:

```text
business_rule_decisions_total{
  rule="refund_approval_required",
  operation="refund",
  entrypoint="api",
  decision="deny",
  reason="approval_missing"
} 42
```

Nếu nền tảng hỗ trợ exemplar liên kết metric với trace, đường truy cập trace vẫn phải được kiểm soát. Người được xem biểu đồ tổng hợp không tự được quyền đọc mọi chi tiết của trace được liên kết.

Metric tổng hợp cũng có thể tiết lộ thông tin nếu nhóm rất nhỏ, ví dụ biểu đồ theo một tenant chỉ có một người dùng. Giảm cardinality và bảo vệ riêng tư có liên quan, nhưng không phải cùng một vấn đề.

### 6.5. Queue, dead-letter queue và file tạm

Một sự kiện đã được làm sạch trong dashboard có thể vẫn tồn tại nguyên bản ở các lớp trung gian:

```text
stdout hoặc file cục bộ
→ agent buffer
→ collector queue
→ dead-letter queue
→ chỉ mục tìm kiếm
→ cache kết quả truy vấn
→ file export hoặc bản sao lưu
```

Chỉ đưa sự kiện đã chọn trường và xử lý an toàn vào pipeline. Bảo vệ queue, spool trên đĩa và dead-letter queue bằng quyền đọc, mã hóa và thời hạn phù hợp. Thông báo sự kiện không hợp lệ nên chứa mã lỗi schema và metadata tối thiểu, không nhúng lại payload gốc.

Debug dump, heap dump và core dump cũng có thể chứa dữ liệu trước khi redaction. Chúng cần cơ chế cấp quyền và lưu giữ riêng; không mặc định an toàn chỉ vì file được tạo để chẩn đoán.

## 7. Ví dụ tạo sự kiện có kiểm soát trong Java

Mã giả sau minh họa việc ánh xạ rõ ràng từ ngữ cảnh đã xác minh sang sự kiện telemetry. Các kiểu được giả định nhằm diễn đạt thiết kế, không phụ thuộc một thư viện cụ thể:

```java
public void recordRefundApprovalDecision(
        VerifiedBusinessContext context,
        ValidatedRuleResult result) {

    // Ranh giới best-effort bao gồm tạo reference và serialize.
    decisionTelemetry.tryBuildAndEmitSanitized(() -> DecisionEvent.of(
        1,
        eventIds.nextServerEventId(),
        clock.instant(),
        correlation.currentServerReference(),
        references.forTenant(context.tenantId()),
        references.forActor(
            context.tenantId(), context.actorId()),
        references.forObject(
            context.tenantId(),
            ObjectKind.REFUND_REQUEST,
            context.refundRequestId()),
        Operation.REFUND,
        RuleId.REFUND_APPROVAL_REQUIRED,
        result.decision(),
        result.reason(),
        policy.auditRevision(),
        EntryPoint.API
    ));
}
```

`ValidatedRuleResult` là kết quả đã được lớp nghiệp vụ kiểm tra hợp đồng decision/reason; việc kiểm tra đó không được giao cho telemetry. Adapter `tryBuildAndEmitSanitized` bao trọn bước ánh xạ, tạo reference và serialize: lỗi ở các bước này phải được xử lý theo hợp đồng best-effort, không fallback sang dữ liệu thô hoặc đổi quyết định nghiệp vụ.

`VerifiedBusinessContext` phải được tạo sau khi xác thực và xác định tenant, actor, đối tượng. Không đổi tên DTO từ client thành “verified” rồi coi là đã an toàn. Với yêu cầu trỏ sang đối tượng không thuộc quyền, chỉ thu thập dữ kiện được phép biết; không nạp thêm chi tiết đối tượng của người khác chỉ để điền log.

`references` thực hiện chính sách tạo tham chiếu đã xác định. Enum và schema ngăn việc thêm chuỗi tùy ý vào event. Khi schema được mở rộng, field mới cần được đánh giá mục đích và mức nhạy cảm trước khi phát hành.

Publisher không nhận cả `request`, `command`, `headers` hoặc `Throwable`. Nếu serialize thất bại, nó chỉ phát chẩn đoán an toàn như `telemetry_schema_encode_failed`; không in đối tượng gốc. Nếu sự kiện là audit bắt buộc, dùng hợp đồng lưu bền vững riêng thay vì dựa vào một phương thức best-effort.

## 8. Chống chèn nội dung và lạm dụng pipeline

Kẻ tấn công có thể gửi tên giả chứa xuống dòng, ký tự điều khiển hoặc JSON trông giống một sự kiện thành công. Ghép chuỗi trực tiếp có thể làm người đọc hoặc parser hiểu sai ranh giới bản ghi:

```text
input giả định:
  bad-value\r\nlevel=INFO event=approval_granted
```

Structured logging với encoder đúng giúp giữ dữ liệu trong một field và escape ký tự điều khiển. Tuy nhiên, nó không tự bảo vệ bí mật: một token được escape đúng vẫn là token bị lộ.

Cần kết hợp:

- Field được cho phép và nguồn dữ liệu rõ ràng.
- Giới hạn độ dài, kiểu và tập giá trị trước khi serialize.
- Encoder và trình xem hiển thị an toàn, không diễn giải dữ liệu thành lệnh hoặc markup.
- Truy vấn tham số hóa hoặc cơ chế dựng truy vấn an toàn khi tra cứu theo input; không ghép dữ liệu người dùng vào query của kho log.
- Hạn mức buffer, số sự kiện và chi phí xử lý để yêu cầu bị chặn không làm đầy đĩa hoặc bộ nhớ.

Mã sự kiện như `approval_granted` phải do máy chủ phát từ một luồng có thẩm quyền. Client không được chọn event name, decision hoặc actor để mạo danh một sự kiện nghiệp vụ thành công.

Giới hạn hoặc sampling log chẩn đoán có thể cần thiết khi bị flood. Cần công bố phần dữ liệu nào có thể thiếu; không sampling tùy ý audit bắt buộc hoặc counter rồi vẫn trình bày chúng như bằng chứng đầy đủ.

## 9. Quyền truy cập phải đi theo dữ liệu qua mọi hệ thống

### 9.1. Quyền xem dashboard không tương đương quyền đọc chi tiết

Một mô hình phân tầng có thể là:

| Nhóm quyền | Phạm vi thông tin |
|---|---|
| Theo dõi vận hành thông thường | Metric tổng hợp và log đã giảm dữ liệu |
| Điều tra sự cố ứng dụng | Log/trace cần thiết, theo service và môi trường được giao |
| Điều tra an ninh hoặc nghiệp vụ | Audit và dữ kiện bổ sung theo vụ việc, có ghi nhận truy cập |
| Quản trị nền tảng telemetry | Quản lý hạ tầng; quyền đọc dữ liệu nhạy cảm cần được xem xét riêng |

Không mặc định người quản lý collector cần quyền giải mã mọi audit record. Tách quyền quản trị hạ tầng, quyền đọc dữ liệu và quyền quản lý khóa khi thiết kế cho phép.

Với hệ thống nhiều tenant, giới hạn truy vấn phải được thực thi ở backend hoặc tầng phân quyền đáng tin cậy. Bộ lọc tenant trong giao diện không đủ nếu người dùng có thể sửa query hoặc gọi API của kho log trực tiếp.

Tham chiếu tenant hoặc actor trong log không phải bằng chứng cấp quyền. Một reference khó đoán cũng không thay thế kiểm tra người đọc có quyền xem dữ liệu đó.

### 9.2. Các đường xuất dữ liệu cũng cần kiểm soát

Quyền đọc cần áp dụng cho dashboard chia sẻ, liên kết trace, API truy vấn, file CSV, report, ảnh chụp màn hình và file đính kèm của công cụ hỗ trợ. Chia sẻ một dashboard riêng tư bằng URL công khai có thể phá vỡ toàn bộ mô hình phân quyền của kho phía sau.

Export phải giới hạn phạm vi, chọn cột và thời gian phù hợp; có chính sách hết hạn và ghi nhận người tạo khi cần. Không gửi log thô sang một hệ thống khác chỉ vì hệ thống đó tiện tìm kiếm hơn.

Đối với trường hợp cần nâng quyền điều tra, có thể dùng quyền có thời hạn, phạm vi vụ việc rõ ràng và audit truy cập. Không dùng tài khoản hỗ trợ dùng chung để mất khả năng biết ai đã đọc hoặc xuất dữ liệu.

### 9.3. Bảo mật truyền tải và tính đáng tin của nguồn phát

Kết nối ứng dụng, collector và kho lưu cần được xác thực và bảo vệ khi truyền. Quyền ghi chỉ cấp cho producer phù hợp; người xem dashboard không được tự tạo một event trông như do service nghiệp vụ phát ra.

Mã hóa khi lưu bảo vệ dữ liệu trên phương tiện lưu trữ, nhưng không ngăn một tài khoản có quyền truy vấn quá rộng. HMAC trên định danh chỉ giúp tạo reference; nó không chứng minh toàn bộ log event chưa bị sửa.

Nếu audit cần chống sửa hoặc phát hiện can thiệp, phải thiết kế riêng cơ chế như quyền chỉ ghi nối tiếp, kiểm soát xóa, nguồn phát xác thực, xác minh tính toàn vẹn và quan sát các khoảng trống sự kiện. Không suy diễn rằng dùng JSON hoặc có event ID là đủ để tạo bằng chứng chống giả mạo.

## 10. Vòng đời dữ liệu, lưu giữ và xóa

### 10.1. Xác định chính sách theo mục đích

Một loại dữ liệu được phép tồn tại trong audit không tự được giữ cùng thời gian ở mọi bản sao chẩn đoán. Có thể phân chia chính sách như sau:

| Kho dữ liệu | Mục đích | Điều cần quyết định |
|---|---|---|
| Log chẩn đoán | Sửa lỗi và điều tra vận hành | Trường tối thiểu, thời gian ngắn phù hợp, giới hạn tìm kiếm |
| Trace | Phân tích luồng và độ trễ | Sampling, thuộc tính, thời gian lưu và quyền drill-down |
| Audit nghiệp vụ | Giải thích quyết định và thay đổi quan trọng | Độ đầy đủ, tính toàn vẹn, lưu giữ và quyền đọc chuyên biệt |
| Metric tổng hợp | Theo dõi xu hướng | Nhãn, mức tổng hợp và thời gian còn hữu ích |
| Queue, spool, dead-letter queue | Chuyển tiếp hoặc xử lý lỗi | Dung lượng, quyền đọc, thời hạn và quy trình thu dọn |
| Export, snapshot, backup | Chia sẻ có kiểm soát hoặc khôi phục | Danh sách bản sao, quyền truy cập, thời điểm hết hạn |

Không đặt một thời gian lưu duy nhất chỉ vì hệ thống tìm kiếm hỗ trợ nó. Quyết định cần gắn với mục đích và yêu cầu cụ thể của hệ thống, không với khả năng giữ dữ liệu vô hạn của hạ tầng.

### 10.2. Xóa ở chỉ mục không có nghĩa xóa hết bản sao

Một quy trình xóa hoặc thu hẹp dữ liệu phải biết những nơi đã nhận sự kiện: hot index, archive, cache truy vấn, spool, dead-letter queue, export và backup. Một bản ghi biến mất khỏi màn hình tìm kiếm vẫn có thể tồn tại trong file tải về.

Nếu backup không thể xóa chọn lọc ngay, cần kiểm soát quyền, thời gian hết hạn và quy trình khôi phục để dữ liệu đã được đánh dấu xử lý không quay lại chỉ mục một cách vô điều kiện. Lời hứa với người dùng và nội bộ phải phản ánh khả năng thực tế của hệ thống.

Rotation khóa HMAC không xóa các reference cũ hoặc ngăn người đã có bản sao liên kết chúng với nhau. Mã hóa bằng khóa dùng chung cũng không tự cho phép xóa riêng dữ liệu của một chủ thể bằng cách hủy khóa mà không ảnh hưởng người khác. Nếu thiết kế dựa vào hủy khóa để xử lý dữ liệu, phải xác định cấu trúc khóa và bản sao khóa tương ứng ngay từ đầu.

Không tạo thêm một bảng ánh xạ đầy đủ mọi dữ liệu cá nhân chỉ để dễ tra log. Nếu có nhu cầu tìm hoặc xử lý sự kiện theo chủ thể, thiết kế khả năng tra cứu đó trong phạm vi hẹp, có quyền truy cập và vòng đời riêng.

## 11. Lỗi telemetry và audit bắt buộc có hợp đồng khác nhau

### 11.1. Telemetry chẩn đoán thường là best-effort

Nếu collector không nhận được dữ liệu, thao tác nghiệp vụ không được tự đổi từ `deny` thành `allow`. Tương tự, exception của logger không nên che lỗi gốc hoặc làm trả nhầm kết quả thành công.

Với sự kiện chẩn đoán tùy chọn, có thể dùng queue giới hạn và bỏ bớt theo chính sách khi đầy. Tín hiệu bị bỏ cần được quan sát qua một cơ chế phù hợp, nhưng không ghi lại payload gốc để báo rằng payload đã bị mất.

Không gọi mạng đồng bộ không giới hạn để gửi log trong transaction hoàn tiền. Tình trạng hệ thống quan sát chậm không nên giữ khóa nghiệp vụ lâu ngoài thiết kế.

### 11.2. Audit bắt buộc là điều kiện được thiết kế trước

Một số thao tác có thể yêu cầu bản ghi audit bền vững đi cùng thay đổi nghiệp vụ. Khi đó, thiết kế cần nêu rõ thao tác có bị từ chối nếu không ghi được audit hay không.

Ví dụ, transaction có thể ghi thay đổi trạng thái và một audit outbox đã được giảm dữ liệu trong cùng cơ sở dữ liệu. Chỉ sau commit, publisher mới chuyển event sang kho audit:

```text
Transaction:
  kiểm tra quyền và bất biến
  → ghi thay đổi nghiệp vụ
  → ghi audit outbox đã chọn trường
  → commit

Publisher:
  đọc outbox đã commit
  → gửi tới kho audit được bảo vệ
  → đánh dấu chuyển tiếp theo giao thức retry
```

Nếu không thể ghi outbox và hợp đồng yêu cầu nó là bắt buộc, transaction phải rollback theo thiết kế. Nếu exporter chỉ lỗi sau commit, không được nói tác động nghiệp vụ đã rollback; outbox cần retry và cảnh báo backlog.

Retry có thể chuyển một event nhiều lần. Event ID ổn định và xử lý trùng ở bên nhận giúp giữ nghĩa sự kiện, không có nghĩa pipeline mặc nhiên đạt exactly-once. Mọi bản sao outbox và queue vẫn phải tuân theo chính sách dữ liệu nhạy cảm.

Đừng gom kênh audit bắt buộc với debug log rồi đặt chung một chính sách drop hoặc sampling. Cũng không áp dụng việc chặn nghiệp vụ khi mọi log chẩn đoán lỗi nếu sản phẩm chưa có yêu cầu như vậy.

## 12. Khi phát hiện đã ghi dữ liệu nhạy cảm

Xử lý sự cố cần đồng thời ngăn phát sinh thêm, hạn chế truy cập và đánh giá phần dữ liệu đã lan truyền. Một trình tự thực tế:

1. **Chặn nguồn phát:** sửa hoặc tắt đường capture gây lộ, bao gồm middleware, auto-instrumentation và chế độ debug. Bộ lọc cuối pipeline chỉ là biện pháp bổ sung.
2. **Giới hạn tiếp cận:** thu hẹp quyền truy vấn, chia sẻ và export của tập dữ liệu liên quan; giữ thông tin phục vụ điều tra trong kênh phù hợp.
3. **Đánh giá phạm vi:** xác định service, thời gian, trường bị lộ, queue, chỉ mục, file export và bên nhận nào có thể đã nhận dữ liệu.
4. **Vô hiệu hóa khả năng truy cập nếu cần:** thu hồi hoặc thay mới token, session hay khóa đã lộ theo loại bí mật và phạm vi ảnh hưởng. Xóa log không làm một token đã bị sao chép mất hiệu lực.
5. **Xử lý các bản sao:** làm sạch hoặc giới hạn dữ liệu theo quy trình đã xác định, bao gồm cache, spool, dead-letter queue và chính sách backup; phối hợp với yêu cầu giữ bằng chứng điều tra.
6. **Xác minh bằng dữ liệu kiểm thử:** chứng minh nguồn đã được sửa và pipeline không tiếp tục nhận trường nhạy cảm.

Không sao chép token hoặc payload thật vào ticket, chat, ảnh chụp màn hình hay lệnh terminal để mô tả sự cố. Dùng event ID, phạm vi thời gian và mẫu đã che; người điều tra có quyền truy cập dữ kiện gốc theo quy trình phù hợp.

Thay đổi một regex không đủ để kết luận sự cố kết thúc. Cần kiểm tra các dạng mã hóa, alias field, trường lồng nhau, exception và đường thu thập tự động đã gây lộ ban đầu.

## 13. Kiểm thử bằng dữ liệu tổng hợp và các đường thực thi thật

### 13.1. Tạo dấu kiểm thử thay cho bí mật thật

Có thể dùng các chuỗi tổng hợp dễ nhận diện trong môi trường kiểm thử:

```text
password field: CANARY_PASSWORD_NOT_A_REAL_SECRET_81
Authorization: Bearer CANARY_TOKEN_NOT_A_REAL_TOKEN_81
idempotency key: CANARY_CLIENT_KEY_CONTAINS_PERSONAL_DATA_81
nested metadata: CANARY_NESTED_SENSITIVE_VALUE_81
exception message: CANARY_PARTNER_RESPONSE_VALUE_81
```

Đặt canary ở header, query string, body lồng nhau, response dependency và exception. Cho yêu cầu đi qua gateway, ứng dụng, collector và kho kiểm thử rồi tìm dấu đó ở các điểm xuất được phép kiểm tra. Mục tiêu là không xuất hiện ở nơi hợp đồng cấm thu thập, kể cả stdout, buffer lỗi hoặc dead-letter queue.

Không dùng token production hoặc dữ liệu cá nhân thật để thử bộ lọc. Nếu có đường dữ liệu được biến đổi như mã hóa hoặc escape, kiểm thử cần bao phủ dạng biểu diễn đó; tìm một chuỗi literal đơn thuần không chứng minh mọi dạng rò rỉ đã được ngăn chặn.

### 13.2. Kiểm tra cả bảo mật dữ liệu lẫn giá trị điều tra

| Tình huống | Kết quả cần quan sát |
|---|---|
| Hoàn tiền bị chặn vì thiếu phê duyệt | Có rule, decision, reason và correlation phù hợp; không có payload gốc |
| Client thay tenant hoặc actor trong request | Telemetry không mạo danh ngữ cảnh đã xác minh và không tiết lộ chi tiết đối tượng khác |
| DTO được thêm trường số tài khoản | Schema telemetry không tự thêm trường đó |
| Token nằm trong query string hoặc header | Gateway, access log, span và ứng dụng không ghi giá trị |
| Secret xuất hiện trong exception lồng nhau | Không lọt qua message, cause chain hoặc fallback logger |
| Trace baggage chứa dữ liệu nhạy cảm | Không được lan truyền hoặc xuất tùy ý sang dịch vụ khác |
| Input có xuống dòng, control character hoặc JSON giả | Không tạo thêm bản ghi giả hoặc trường hệ thống bị ghi đè |
| Input rất dài hoặc reason tùy ý | Bị giới hạn; không tăng số nhãn metric theo input |
| Cùng đối tượng trong cùng phạm vi HMAC | Reference nhất quán theo hợp đồng, không lộ ID gốc |
| Cùng ID nhưng khác tenant hoặc loại đối tượng | Reference tách biệt theo domain đã định nghĩa |
| Khóa reference không sẵn sàng | Không fallback sang ID thô; hành vi theo chính sách kênh dữ liệu |
| Người có quyền tenant A mở trace hoặc export tenant B | Backend từ chối, không chỉ ẩn dữ liệu ở giao diện |
| Collector lỗi hoặc buffer đầy | Không ghi raw event sang file phụ, không thay quyết định nghiệp vụ |
| Audit bắt buộc không ghi được | Thao tác xử lý đúng hợp đồng transaction đã thiết kế |
| Khôi phục backup hoặc replay queue | Không vô tình tái đưa dữ liệu đã hết vòng đời vào nơi phục vụ truy vấn |

Kiểm thử reference cũng phải xem xét rotation, khả năng tra cứu và quyền truy cập khóa; chỉ thấy chuỗi “khác ID gốc” chưa đủ để chứng minh thiết kế giảm liên kết đúng mục tiêu.

Để giữ khả năng điều tra, cần kiểm tra chiều ngược lại: sự kiện đã làm sạch vẫn cho biết đúng rule và lý do, có thể nối tới lần thử phù hợp và không bị gọi nhầm là một commit. Redaction quá rộng làm mọi reason biến thành `unknown` sẽ giảm đáng kể giá trị phát hiện lạm dụng.

### 13.3. Debug tạm thời không được mở lại đường lộ dữ liệu

Một cấu hình debug phục vụ sự cố cần giới hạn service, phạm vi, thời gian hiệu lực và người được dùng. Tăng độ chi tiết có thể là bổ sung mã nhánh hoặc thời lượng bước xử lý, không nhất thiết bật ghi body.

Các giới hạn nên được thực thi phía máy chủ. Không để một header từ client bật capture payload, thay đổi nhãn metric hoặc kéo dài vô hạn cửa sổ debug. Khi hết hạn, dữ liệu đã thu thập vẫn phải tuân theo chính sách quyền truy cập và lưu giữ, không trở thành bản sao bị quên.

## 14. Tự đối chiếu trước khi đưa vào vận hành

1. Mỗi field được thu thập để trả lời câu hỏi điều tra cụ thể nào?
2. Những bí mật nào bị loại bỏ trước lần ghi đầu tiên, kể cả gateway và auto-instrumentation?
3. Metric có nhãn hữu hạn và không mang định danh chủ thể, kể cả dưới dạng pseudonym không?
4. Correlation, actor và object reference bắt nguồn từ đâu; chúng có thể bị client mạo danh không?
5. Có đang dùng hash, masking hoặc mã hóa như lý do giữ dữ liệu không cần thiết không?
6. Ai đọc được log, trace, audit và export; quyền có được thực thi ở backend không?
7. Schema có ngăn field mới, exception hoặc metadata tùy ý tự chảy vào pipeline không?
8. Queue, dead-letter queue, file tạm, cache và backup có cùng chính sách bảo vệ dữ liệu không?
9. Kênh best-effort và audit bắt buộc có hợp đồng lỗi, lưu bền vững và sampling riêng không?
10. Khi phát hiện rò rỉ, có thể chặn nguồn, xác định bản sao và vô hiệu hóa bí mật đã lộ không?

Thiết kế tốt giữ lại thông tin về quyết định và tác động cần điều tra, đồng thời giới hạn khả năng đọc, liên kết và tái sử dụng dữ liệu. Quyền theo đối tượng, tenant và bất biến nghiệp vụ phải tiếp tục được bảo vệ khi dữ liệu đi từ ứng dụng sang toàn bộ hệ thống quan sát.
