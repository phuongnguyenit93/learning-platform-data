# Kiểm toán quyết định

Trong một hệ thống sử dụng DSL luật và quyết định (*rules and decision DSL*), **kiểm toán quyết định** (*decision auditing*) là khả năng ghi nhận và truy vết một quyết định đã được tạo ra: hệ thống nhận dữ liệu nào, dùng phiên bản luật nào, những rule nào được đánh giá hoặc kích hoạt, dữ liệu nào làm bằng chứng, kết quả cuối cùng là gì và ai hoặc thành phần nào đã yêu cầu xử lý.

Ví dụ, một hệ thống xét duyệt đơn hàng có thể dùng DSL:

~~~text
decision OrderApproval {
    input {
        amount: Money
        customerRisk: RiskLevel
        country: Country
    }

    rule HighValueReview {
        when amount > 10000
        then requireManualReview("high-value order")
    }

    rule BlockHighRisk {
        when customerRisk == HIGH
        then reject("high risk")
    }

    default approve()
}
~~~

Khi một đơn hàng bị từ chối, người vận hành cần trả lời được: giá trị customerRisk là gì tại thời điểm xét duyệt, rule BlockHighRisk thuộc phiên bản nào, nó có thực sự được kích hoạt không, quyết định có bị một rule ưu tiên cao hơn ghi đè không và kết quả đã được gửi đến hệ thống nào.

Chỉ lưu kết quả cuối cùng như REJECTED là chưa đủ để giải thích quyết định. Một bản ghi kiểm toán tốt giữ được ngữ cảnh và nguồn gốc của kết quả, đồng thời bảo đảm rằng thông tin được lưu có thể kiểm tra lại mà không làm lộ dữ liệu nhạy cảm.

## 1. Vì sao cần kiểm toán quyết định?

Rule engine thường tự động đánh giá nhiều điều kiện và kết hợp kết quả theo thứ tự, priority hoặc policy. Khi số lượng rule tăng, người vận hành khó biết vì sao một quyết định được đưa ra nếu hệ thống chỉ trả về kết quả cuối cùng.

Kiểm toán quyết định phục vụ nhiều mục đích:

- Giải thích vì sao hệ thống chấp nhận, từ chối, phân loại hoặc chuyển tiếp một trường hợp.
- Điều tra lỗi nghiệp vụ và sự cố vận hành.
- Chứng minh quyết định được tạo bằng đúng phiên bản policy có hiệu lực.
- Phát hiện thay đổi ngoài dự kiến sau khi rule được cập nhật.
- Hỗ trợ kiểm tra tuân thủ và yêu cầu quản trị.
- Tái dựng hoặc so sánh quyết định trong môi trường kiểm thử.
- Xác định rule nào đang được sử dụng, rule nào không còn được kích hoạt.
- Hỗ trợ người dùng khiếu nại hoặc yêu cầu xem xét lại.

### 1.1. Quyết định tự động cần có dấu vết

Giả sử một hệ thống chấm điểm tín dụng trả về:

~~~json
{
  "applicationId": "APP-1042",
  "decision": "DECLINED"
}
~~~

Bản ghi này cho biết kết quả, nhưng không cho biết nguyên nhân. Nếu sau đó policy thay đổi, nhóm hỗ trợ không thể xác định liệu quyết định cũ có được tạo theo policy hiện tại hay policy trước đó.

Một bản ghi có khả năng kiểm toán cần thêm decision ID, thời điểm, policy version, input reference, rule execution trace và reason code.

### 1.2. Phân biệt audit với logging thông thường

Log vận hành thường giúp tìm lỗi kỹ thuật: request timeout, exception, retry hoặc thời gian xử lý. Audit record ghi lại sự kiện có ý nghĩa đối với quyết định và trách nhiệm giải trình.

| Khía cạnh | Operational log | Decision audit |
|---|---|---|
| Mục đích | Điều tra hoạt động kỹ thuật | Giải thích và truy vết quyết định |
| Nội dung | Stack trace, latency, request flow | Input, policy, rule, outcome |
| Định danh | Process, request, trace ID | Decision ID, case ID, policy ID |
| Vòng đời | Có thể xoay vòng nhanh | Theo retention policy nghiệp vụ |
| Tính toàn vẹn | Phụ thuộc hệ thống log | Thường cần kiểm soát chống sửa đổi |
| Người sử dụng | Developer, SRE | Operations, auditor, compliance, analyst |

Hai loại dữ liệu có thể liên kết qua correlation ID, nhưng không nên mặc định log kỹ thuật thay thế audit record.

### 1.3. Audit không đồng nghĩa với ghi mọi thứ

Ghi toàn bộ request, response, biến nội bộ và secret có thể làm tăng chi phí, tạo rủi ro riêng tư và khiến việc tìm thông tin quan trọng khó hơn. Mục tiêu là ghi đủ dữ liệu để giải thích quyết định theo policy, với mức chi tiết và thời gian lưu phù hợp.

## 2. Những thành phần của một decision audit record

Một audit record thường chứa nhiều nhóm thông tin có quan hệ với nhau.

| Nhóm | Nội dung |
|---|---|
| Identity | Decision ID, case ID, request ID |
| Time | Thời điểm yêu cầu, bắt đầu, kết thúc |
| Actor | Người dùng, dịch vụ hoặc hệ thống khởi tạo |
| Context | Tenant, môi trường, loại nghiệp vụ |
| Input | Snapshot hoặc tham chiếu đến input đã dùng |
| Policy provenance | Decision model, policy version, artifact hash |
| Execution | Rule evaluated, matched, skipped hoặc failed |
| Evidence | Điều kiện và giá trị liên quan đến kết quả |
| Outcome | Quyết định, reason code, trạng thái |
| Integrity | Sequence, checksum, signature hoặc hash chain |
| Correlation | Trace ID, event ID, downstream operation ID |

Không phải mọi hệ thống đều cần tất cả trường. Schema audit cần được thiết kế theo yêu cầu giải trình, quy định lưu trữ và khả năng xử lý dữ liệu.

### 2.1. Decision ID

Mỗi lần đánh giá nên có một định danh duy nhất. Decision ID phân biệt một lần thực thi với các lần đánh giá lại cùng một hồ sơ.

Ví dụ:

~~~text
decisionId = "dec-01J9K8..."
caseId = "APP-1042"
~~~

Một case có thể có nhiều decision record nếu dữ liệu được cập nhật, policy thay đổi hoặc người dùng yêu cầu xem xét lại.

### 2.2. Thời điểm

Nên phân biệt thời điểm yêu cầu được tiếp nhận, engine bắt đầu đánh giá, đánh giá kết thúc, quyết định được ghi nhận bền vững và thời điểm quyết định có hiệu lực nghiệp vụ nếu khác thời điểm xử lý.

Timestamp nên có timezone rõ ràng, thường lưu theo UTC. Hệ thống phân tán cũng cần lưu ý clock skew và thứ tự sự kiện.

### 2.3. Actor và nguồn yêu cầu

Actor có thể là người dùng, service account, workflow hoặc batch job. Không nên chỉ lưu tên hiển thị; cần lưu định danh phù hợp với hệ thống identity và tenant.

### 2.4. Correlation ID

Correlation ID liên kết quyết định với request, workflow, message hoặc transaction bên ngoài. Nó giúp truy vấn toàn bộ luồng xử lý mà không phải dựa vào thời gian gần đúng.

## 3. Ghi nhận input của quyết định

Muốn giải thích một quyết định, trước hết phải biết engine đã nhận dữ liệu nào. Có hai cách phổ biến:

1. Lưu snapshot input trực tiếp trong audit record.
2. Lưu reference đến một bản dữ liệu bất biến đã được lưu ở nơi khác.

### 3.1. Input snapshot

Snapshot ghi lại các giá trị thực sự được dùng khi đánh giá:

~~~json
{
  "applicationId": "APP-1042",
  "amount": 12500,
  "currency": "USD",
  "customerRisk": "HIGH",
  "country": "VN"
}
~~~

Snapshot giúp giải thích quyết định ngay cả khi hồ sơ gốc được cập nhật sau đó. Tuy nhiên, nó có thể chứa dữ liệu cá nhân hoặc bí mật, vì vậy cần chọn field, mã hóa và giới hạn quyền truy cập.

### 3.2. Input reference

Thay vì sao chép dữ liệu, audit record có thể lưu:

~~~json
{
  "inputReference": {
    "system": "application-store",
    "recordId": "APP-1042",
    "revision": 17
  }
}
~~~

Reference chỉ có ích nếu revision được giữ bất biến và có thể truy xuất trong suốt thời gian retention. Nếu chỉ trỏ đến bản ghi hiện tại, dữ liệu có thể đã đổi và không còn phản ánh input lúc quyết định được tạo.

### 3.3. Snapshot hay reference?

| Tiêu chí | Snapshot | Reference |
|---|---|---|
| Tự chứa | Cao | Phụ thuộc hệ thống ngoài |
| Dung lượng audit | Lớn hơn | Nhỏ hơn |
| Dữ liệu nhạy cảm | Có thể sao chép thêm | Có thể giảm sao chép |
| Khả năng truy xuất lâu dài | Tốt nếu lưu bền vững | Phụ thuộc retention của nguồn |
| Tính nhất quán lịch sử | Rõ nếu snapshot bất biến | Cần revision bất biến |

Một hệ thống có thể dùng kết hợp: snapshot các field ảnh hưởng trực tiếp đến rule và reference đến hồ sơ đầy đủ.

### 3.4. Input đã chuẩn hóa

Engine có thể chuẩn hóa input trước khi đánh giá, ví dụ chuyển currency, chuẩn hóa mã quốc gia hoặc áp dụng default. Audit nên phân biệt:

- Giá trị raw nhận từ nguồn.
- Giá trị sau validation/normalization.
- Giá trị cuối cùng mà rule engine thực sự dùng.

Nếu chỉ lưu raw input, auditor có thể không tái hiện được điều kiện đã được đánh giá. Nếu chỉ lưu normalized input, có thể mất thông tin về dữ liệu nguồn. Chọn mức lưu dựa trên yêu cầu giải trình.

### 3.5. Input thiếu hoặc không hợp lệ

Audit cần ghi nhận field bị thiếu, không parse được hoặc bị thay thế bằng default. Không nên ghi một giá trị default như thể người dùng đã cung cấp nó.

## 4. Ghi nhận nguồn gốc của policy và rule

Một quyết định chỉ có thể được giải thích chính xác khi biết chính sách nào đã được sử dụng.

Thông tin provenance thường gồm:

- Decision model hoặc policy ID.
- Version hoặc revision.
- Artifact hash.
- Module và dependency version.
- Compiler/runtime version nếu ảnh hưởng semantics.
- Môi trường triển khai.
- Thời điểm policy được publish hoặc activate.
- Thời gian hiệu lực nghiệp vụ nếu có.

### 4.1. Policy version

Ví dụ:

~~~text
decisionModel = "OrderApproval"
policyVersion = "3.7.2"
~~~

Chỉ lưu tên OrderApproval là chưa đủ nếu nội dung rule có thể thay đổi theo thời gian.

### 4.2. Artifact hash

Hash của artifact đã compile giúp nhận diện chính xác nội dung policy được thực thi. Hai môi trường có thể cùng khai báo version string nhưng chứa artifact khác nhau nếu quá trình build hoặc publish sai.

Hash không thay thế chữ ký số hoặc kiểm soát nguồn phát hành. Nó là định danh nội dung để đối chiếu.

### 4.3. Dependency provenance

Một decision model có thể import module rule hoặc bảng quyết định từ package khác. Audit nên ghi các dependency version có ảnh hưởng đến kết quả.

### 4.4. Compiler và runtime version

Nếu compiler thay đổi cách diễn giải expression hoặc runtime thay đổi thứ tự thực thi, cùng source policy có thể tạo kết quả khác. Khi cần tái dựng chính xác, version của engine và artifact cần được ghi nhận.

### 4.5. Effective time

Một policy có thể được publish hôm nay nhưng chỉ có hiệu lực từ ngày mai. Audit cần phân biệt thời điểm publish, thời điểm activate và thời điểm hiệu lực được dùng khi đánh giá.

## 5. Ghi nhận rule execution

Trong rule engine, một quyết định có thể đánh giá nhiều rule. Audit trace cần cho biết rule nào được kiểm tra và kết quả đánh giá ra sao.

Các trạng thái thường gặp:

- Evaluated: rule đã được đánh giá.
- Matched: điều kiện của rule đúng.
- Not matched: điều kiện sai.
- Skipped: rule không được đánh giá do điều kiện điều khiển hoặc short-circuit.
- Failed: quá trình đánh giá rule gặp lỗi.
- Suppressed: kết quả hoặc hành động bị policy khác chặn.

Tên trạng thái có thể khác nhau giữa engine, nhưng semantics cần được định nghĩa rõ.

### 5.1. Matched và not matched

Ví dụ:

~~~text
rule HighValueReview {
    when amount > 10000
    then requireManualReview("high-value order")
}
~~~

Nếu amount là 12500, rule matched. Nếu amount là 250, rule not matched.

Audit record có thể ghi:

~~~json
{
  "ruleId": "HighValueReview",
  "ruleVersion": "3.7.2",
  "status": "MATCHED"
}
~~~

### 5.2. Skipped khác not matched

Not matched nghĩa là điều kiện đã được đánh giá và kết quả là false. Skipped nghĩa là điều kiện không được đánh giá. Hai trạng thái này không thể thay thế nhau khi giải thích.

Ví dụ, một rule nằm sau nhánh stop có thể bị skipped. Nếu audit ghi not matched, người đọc sẽ hiểu nhầm rằng điều kiện đã được kiểm tra.

### 5.3. Rule evaluation order

Nếu engine thực thi rule theo priority hoặc thứ tự khai báo, audit nên ghi đủ thông tin để tái dựng thứ tự:

~~~text
1. ValidateCustomer
2. BlockHighRisk
3. HighValueReview
4. DefaultApproval
~~~

Nếu engine dùng agenda hoặc chiến lược conflict resolution, cần ghi thứ tự thực thi thực tế hoặc dữ liệu đủ để tái dựng nó.

### 5.4. Rule priority

Priority có thể ảnh hưởng rule nào chạy trước hoặc rule nào thắng. Audit cần ghi priority có hiệu lực tại thời điểm quyết định, không chỉ priority hiện tại trong source.

### 5.5. Short-circuit và early exit

Một số engine dừng khi gặp rule terminal. Các rule phía sau có thể không chạy. Trace nên ghi lý do kết thúc, chẳng hạn terminal rule matched, decision completed hoặc execution limit reached.

## 6. Ghi nhận evidence và điều kiện đã quyết định

Evidence là dữ liệu hoặc kết quả được dùng để hỗ trợ một kết luận. Với rule engine, evidence thường là các điều kiện đã đánh giá cùng giá trị liên quan.

Ví dụ:

~~~text
rule BlockHighRisk {
    when customerRisk == HIGH
    then reject("high risk")
}
~~~

Evidence có thể gồm:

~~~json
{
  "ruleId": "BlockHighRisk",
  "condition": "customerRisk == HIGH",
  "operands": {
    "customerRisk": "HIGH"
  },
  "result": true
}
~~~

### 6.1. Evidence cần đủ ngữ cảnh

Chỉ lưu result bằng true thường không đủ. Cần biết condition nào đã được kiểm tra, field nào liên quan và giá trị hoặc reference nào được sử dụng.

### 6.2. Giá trị thực tế và giá trị hiển thị

Một hệ thống có thể che dữ liệu trong giao diện audit nhưng vẫn cần lưu evidence an toàn để giải thích. Nên phân biệt dữ liệu gốc được bảo vệ với representation đã redacted hiển thị cho người có quyền hạn thấp hơn.

### 6.3. Derived values

Nếu rule dùng một giá trị đã tính như riskScore, audit cần biết giá trị đó được tạo từ đâu, theo model version nào và có input nào ảnh hưởng.

### 6.4. External evidence

Quyết định có thể phụ thuộc kết quả từ dịch vụ ngoài như fraud score hoặc identity verification. Nên lưu provider, response ID, timestamp, version và trạng thái xác minh, thay vì chỉ lưu một boolean đã chuyển đổi.

### 6.5. Evidence không nhất thiết là toàn bộ dữ liệu

Chỉ lưu field thực sự cần giải thích. Ghi toàn bộ object có thể làm lộ dữ liệu không liên quan và khiến audit record lớn hơn nhiều.

## 7. Decision outcome và reason code

Outcome là kết quả cuối cùng của decision model. Nó có thể là approve/reject, allow/deny, route đến queue hoặc người xử lý, chọn mức giá/hạn mức/nhóm, yêu cầu manual review hoặc trả về nhiều action.

Ví dụ:

~~~json
{
  "decision": "REJECTED",
  "reasonCodes": [
    "CUSTOMER_HIGH_RISK"
  ]
}
~~~

### 7.1. Reason code ổn định

Reason code nên là định danh ổn định, không phải câu văn tự do. Câu giải thích có thể thay đổi theo ngôn ngữ hoặc cách trình bày; code ổn định giúp báo cáo, phân tích và tích hợp.

### 7.2. Nhiều reason cùng lúc

Một quyết định có thể có nhiều nguyên nhân. Cần xác định reason nào là nguyên nhân chính, reason nào bổ sung, có thứ tự ưu tiên hay không và một reason có thể được tạo bởi nhiều rule hay không.

### 7.3. Outcome và action

Outcome nghiệp vụ có thể khác action kỹ thuật. Ví dụ outcome là APPROVED, còn action là gửi lệnh tạo đơn hàng. Audit cần liên kết decision với action và trạng thái thực hiện action.

### 7.4. Quyết định và kết quả downstream

Decision engine có thể trả kết quả thành công nhưng hệ thống downstream thất bại khi thực thi action. Không nên ghi decision thành thất bại nếu policy đã quyết định approve; cần ghi riêng trạng thái action.

## 8. Giải thích quyết định

Decision explanation là phần trình bày vì sao hệ thống đưa ra kết quả. Nó có thể được tạo từ execution trace, evidence và metadata của rule.

Ví dụ:

~~~text
Kết quả: REJECTED

Lý do chính:
- Hồ sơ có mức rủi ro HIGH.

Rule được kích hoạt:
- BlockHighRisk (policy 3.7.2)

Bằng chứng:
- customerRisk = HIGH
- Điều kiện customerRisk == HIGH trả về true
~~~

### 8.1. Explanation khác raw trace

Raw trace chứa chi tiết kỹ thuật của từng bước. Explanation chọn những thông tin quan trọng để người đọc hiểu kết quả.

| Raw trace | Decision explanation |
|---|---|
| Node ID, expression ID, execution timestamp | Lý do nghiệp vụ |
| Từng phép so sánh | Điều kiện quan trọng đã đúng/sai |
| Internal variable | Field hoặc evidence được phép hiển thị |
| Engine scheduling detail | Rule nào ảnh hưởng outcome |

Một hệ thống có thể lưu raw trace với quyền truy cập hạn chế và tạo explanation riêng cho người dùng hoặc auditor.

### 8.2. Explanation phải dựa trên evidence

Không nên sinh câu giải thích bằng cách đoán từ outcome. Nếu audit record nói REJECTED, hệ thống không được tự tạo lý do địa chỉ không hợp lệ khi không có evidence cho điều đó.

### 8.3. Explanation cho rule không match

Trong một số trường hợp, biết rule không match cũng quan trọng. Ví dụ, rule ưu đãi không áp dụng vì tổng đơn thấp hơn ngưỡng. Tuy nhiên, không phải mọi rule không match đều cần hiển thị cho người dùng; nên chọn theo mục đích và quyền truy cập.

### 8.4. Explanation nhiều mức

Có thể có explanation ngắn cho người dùng cuối, explanation nghiệp vụ cho nhân viên hỗ trợ và trace chi tiết cho developer/auditor. Mỗi mức có thể hiển thị lượng thông tin khác nhau nhưng phải xuất phát từ cùng audit facts.

## 9. Thiết kế audit event trong DSL

DSL luật có thể khai báo metadata phục vụ audit ngay trong decision model.

Ví dụ:

~~~text
decision OrderApproval {
    audit {
        enabled = true
        captureInputs = ["amount", "customerRisk", "country"]
        captureRuleResults = true
        captureEvidence = true
        reasonCodes = true
    }

    rule BlockHighRisk {
        @audit(label = "High customer risk")
        when customerRisk == HIGH
        then reject("CUSTOMER_HIGH_RISK")
    }
}
~~~

Đây là cú pháp minh họa. Một DSL thực tế cần xác định metadata nào là compile-time, metadata nào là runtime và ai được phép thay đổi policy audit.

### 9.1. Audit policy

Audit policy quyết định loại quyết định cần audit, trường input nào được lưu, mức chi tiết execution trace, có lưu not-matched rules không, có lưu raw evidence hay chỉ reference, retention period và ai có quyền đọc hoặc export.

### 9.2. Rule annotation

Annotation có thể cung cấp tên hiển thị, reason code, sensitivity hoặc nhóm nghiệp vụ:

~~~text
@audit(
    label = "Customer risk block",
    reasonCode = "CUSTOMER_HIGH_RISK",
    category = "ELIGIBILITY"
)
rule BlockHighRisk {
    when customerRisk == HIGH
    then reject()
}
~~~

### 9.3. Bắt buộc audit cho quyết định quan trọng

Một decision model có thể yêu cầu audit không được tắt trong production:

~~~text
policyAudit {
    required = true
    minimumDetail = RULE_AND_EVIDENCE
}
~~~

Compiler hoặc deployment validator có thể từ chối cấu hình production nếu audit policy không đáp ứng yêu cầu.

### 9.4. Không để rule tự xóa audit

Rule thực thi không nên có quyền tùy tiện bỏ qua audit cho chính quyết định nó tạo ra. Việc thay đổi audit policy cần đi qua quyền quản trị và được ghi nhận riêng.

## 10. Decision audit schema

Audit record nên có schema ổn định để nhiều hệ thống có thể ghi và đọc.

Một ví dụ khái niệm:

~~~json
{
  "auditSchemaVersion": 1,
  "decisionId": "dec-1042-01",
  "caseId": "APP-1042",
  "decisionModel": {
    "id": "OrderApproval",
    "version": "3.7.2",
    "artifactHash": "sha256:..."
  },
  "engine": {
    "name": "rules-runtime",
    "version": "2.6.0"
  },
  "startedAt": "2026-11-15T03:00:00Z",
  "completedAt": "2026-11-15T03:00:00.018Z",
  "outcome": {
    "status": "REJECTED",
    "reasonCodes": ["CUSTOMER_HIGH_RISK"]
  },
  "ruleTrace": [
    {
      "ruleId": "BlockHighRisk",
      "status": "MATCHED"
    }
  ]
}
~~~

### 10.1. Schema version của audit

Audit record có thể tồn tại lâu hơn version của engine. Vì vậy, schema audit cần version riêng để reader mới biết cách giải mã record cũ.

### 10.2. Required fields

Những trường cần thiết để xác định một decision nên bắt buộc, ví dụ decision ID, timestamp, model identity và outcome. Các trường có thể vắng mặt cần được mô tả rõ.

### 10.3. Extension fields

Có thể cho phép extension có namespace để module bổ sung metadata. Tuy nhiên, cần phân biệt field chuẩn với field mở rộng và quy định xử lý unknown field.

### 10.4. Correlation với event schema

Nếu decision phát sinh event, audit record nên giữ event ID hoặc correlation ID để liên kết với message được publish.

## 11. Tính toàn vẹn của audit trail

Audit record chỉ có giá trị nếu có thể tin rằng dữ liệu không bị sửa hoặc xóa trái phép.

### 11.1. Append-only storage

Một mô hình phổ biến là chỉ thêm record mới, không cập nhật record cũ. Nếu có correction, ghi một event mới tham chiếu record gốc và giải thích lý do.

### 11.2. Hash

Có thể tính hash của canonical representation của audit record:

~~~text
recordHash = HASH(canonicalRecord)
~~~

Hash giúp phát hiện thay đổi nếu giá trị tham chiếu được bảo vệ. Nếu kẻ tấn công có thể sửa cả record lẫn hash, hash đơn lẻ không đủ.

### 11.3. Hash chain

Một chuỗi record có thể liên kết hash trước:

~~~text
H0 = initial value
H1 = HASH(record1 || H0)
H2 = HASH(record2 || H1)
H3 = HASH(record3 || H2)
~~~

Sửa một record cũ làm các hash phía sau không còn khớp. Để chống việc viết lại toàn bộ chuỗi, cần bảo vệ checkpoint hoặc root hash bằng chữ ký, kho độc lập hoặc dịch vụ timestamp đáng tin cậy.

### 11.4. Digital signature

Có thể ký record hoặc batch bằng private key của dịch vụ audit. Auditor xác minh chữ ký bằng public key đã tin cậy. Cần quản lý rotation, revocation và thời gian hiệu lực của key.

### 11.5. Access control

Quyền đọc, export, archive và quản trị audit store cần được phân tách. Người tạo quyết định không nên mặc nhiên có quyền sửa audit history.

### 11.6. Immutable backup

Backup hoặc object lock có thể giúp bảo vệ bản lưu lịch sử. Cần kiểm tra khả năng restore và tính toàn vẹn của bản backup.

## 12. Bảo mật và quyền riêng tư

Audit có thể chứa dữ liệu cá nhân, tài chính, thông tin sức khỏe, credential hoặc dữ liệu nghiệp vụ nhạy cảm. Ghi lại dữ liệu không có nghĩa là mọi người đều được quyền xem dữ liệu đó.

### 12.1. Data minimization

Chỉ lưu những trường cần để đáp ứng mục đích audit. Nếu chỉ cần biết risk score thuộc nhóm HIGH, có thể không cần sao chép toàn bộ hồ sơ khách hàng vào audit store.

### 12.2. Masking và redaction

Ví dụ:

~~~json
{
  "account": "****4821",
  "customerRisk": "HIGH",
  "apiKey": "[REDACTED]"
}
~~~

Redaction cần được áp dụng nhất quán ở mọi đường xuất dữ liệu, bao gồm log, API, report và export file.

### 12.3. Pseudonymization

Có thể dùng identifier giả danh để phân tích xu hướng mà không cần hiển thị trực tiếp danh tính. Mapping giữa pseudonymous ID và danh tính thật phải được bảo vệ riêng.

### 12.4. Encryption

Audit record có thể được mã hóa khi truyền và khi lưu. Key management cần tách khỏi dữ liệu, có rotation và kiểm soát quyền truy cập.

### 12.5. Role-based access

Có thể chia quyền:

- Người dùng cuối xem explanation của quyết định liên quan đến họ.
- Nhân viên hỗ trợ xem reason code và evidence đã che dữ liệu.
- Auditor xem trace chi tiết theo phạm vi được cấp.
- Administrator quản lý retention và export.

### 12.6. Không ghi secret vào evidence

Nếu rule kiểm tra một secret, audit thường chỉ cần ghi trạng thái kiểm tra hoặc reference đã bảo vệ. Không nên ghi plaintext secret vào điều kiện hoặc trace.

## 13. Retention và vòng đời audit

Audit record có thể phải được lưu lâu hơn operational logs. Thời gian lưu phụ thuộc loại nghiệp vụ, quy định và mục đích sử dụng.

### 13.1. Retention policy

Retention policy có thể được xác định theo loại decision, mức độ rủi ro, tenant hoặc jurisdiction, trạng thái tranh chấp, nghĩa vụ pháp lý và mục đích phân tích/điều tra.

Không nên chọn một thời hạn duy nhất cho mọi dữ liệu nếu yêu cầu lưu trữ khác nhau.

### 13.2. Archive

Record cũ có thể được chuyển sang storage chi phí thấp hơn. Archive vẫn cần giữ khả năng xác minh integrity và giải mã schema version cũ.

### 13.3. Legal hold

Khi một hồ sơ liên quan đến tranh chấp hoặc điều tra, có thể cần tạm dừng xóa theo retention thông thường. Quy trình legal hold cần được ghi nhận và giới hạn phạm vi.

### 13.4. Deletion và quyền riêng tư

Một số dữ liệu có thể phải xóa hoặc ẩn danh khi hết mục đích lưu. Thiết kế audit cần cân bằng yêu cầu toàn vẹn lịch sử với nghĩa vụ bảo vệ dữ liệu. Có thể tách PII khỏi audit facts, dùng tokenized reference hoặc crypto-shredding theo policy phù hợp.

### 13.5. Schema cũ vẫn phải đọc được

Nếu audit record được giữ nhiều năm, hệ thống cần duy trì reader hoặc migration cho schema cũ. Không nên giả định mọi record đều dùng schema mới nhất.

## 14. Tái dựng và replay quyết định

Tái dựng quyết định (*decision reconstruction*) là quá trình chạy lại logic với dữ liệu và policy lịch sử để kiểm tra kết quả. Replay là thực thi lại một hoặc nhiều sự kiện hoặc input theo một quy trình xác định.

### 14.1. Điều kiện để tái dựng

Muốn tái dựng chính xác thường cần:

- Input snapshot hoặc revision bất biến.
- Decision model version chính xác.
- Dependency versions.
- Compiler/runtime version có liên quan.
- Configuration và environment context.
- External evidence hoặc response snapshot.
- Deterministic execution semantics.

Thiếu một trong các yếu tố có thể khiến replay cho kết quả khác.

### 14.2. Replay với policy hiện tại

Một câu hỏi khác là: “Nếu áp dụng policy hiện tại cho input cũ thì kết quả sẽ ra sao?” Đây là re-evaluation, không phải tái dựng quyết định lịch sử.

Nên lưu cả historical decision (kết quả thật tại thời điểm trước) và re-evaluated decision (kết quả mô phỏng với policy mới). Không ghi đè historical decision bằng kết quả re-evaluation.

### 14.3. External service

Nếu rule gọi fraud service hoặc pricing API, replay gọi lại dịch vụ hiện tại có thể nhận kết quả khác. Muốn tái dựng lịch sử cần lưu response snapshot hoặc immutable response reference.

### 14.4. Side effects

Replay không nên tự động gửi email, trừ tiền hoặc tạo resource lần nữa. Có thể chạy chế độ simulation/no-side-effects, trong đó decision engine chỉ tính outcome và trace.

### 14.5. Determinism

Thời gian hiện tại, random number, thứ tự map, network response và mutable global state có thể làm quyết định không deterministic. DSL nên làm rõ các dependency này và audit context cần ghi lại khi chúng ảnh hưởng kết quả.

## 15. Audit trong hệ thống phân tán

Một decision có thể được xử lý qua nhiều service:

~~~text
API Gateway
    |
    v
Decision Service
    |
    +----> Customer Profile
    |
    +----> Risk Service
    |
    v
Audit Store
    |
    v
Event Bus
    |
    v
Order Service
~~~

### 15.1. Correlation và trace

Mỗi request nên mang correlation ID xuyên qua service. Decision ID gắn với lần đánh giá; trace ID gắn với luồng kỹ thuật rộng hơn.

### 15.2. Event ordering

Event bus có thể giao message trễ hoặc lặp. Audit cần event ID, sequence hoặc timestamp có ý nghĩa để xác định thứ tự. Timestamp đơn lẻ không luôn bảo đảm thứ tự nhân quả.

### 15.3. Exactly-once không nên được giả định

Trong hệ thống phân tán, một event có thể được gửi lại. Consumer audit cần idempotency key hoặc deduplication để tránh tạo nhiều record cho cùng một logical event.

### 15.4. Ghi audit và quyết định trong một transaction

Nếu decision được commit nhưng audit record không được lưu, hệ thống có một quyết định không thể truy vết. Ngược lại, audit ghi thành công nhưng decision bị rollback có thể tạo record gây hiểu nhầm.

Có thể dùng transaction chung nếu cùng datastore, hoặc transactional outbox nếu phải publish sang hệ thống khác.

### 15.5. Transactional outbox

Một service ghi decision và outbox event trong cùng database transaction. Worker sau đó gửi event đến audit store hoặc message broker. Event cần idempotency key để consumer xử lý gửi lại an toàn.

### 15.6. Audit unavailable

Hệ thống cần policy rõ nếu audit store tạm thời không khả dụng:

- Fail closed: không cho quyết định quan trọng hoàn tất nếu không ghi audit.
- Durable local buffer: ghi vào spool bền vững rồi chuyển tiếp.
- Retry có giới hạn: thử lại và phát cảnh báo.

Chọn policy theo mức độ quan trọng của quyết định. Không nên âm thầm bỏ audit mà vẫn báo thành công nếu audit là yêu cầu bắt buộc.

## 16. Kiểm toán các chiến lược thực thi rule

Các engine có cách điều phối rule khác nhau, vì vậy audit trace cần phản ánh đúng semantics.

### 16.1. Sequential rules

Rule được đánh giá theo thứ tự. Trace có thể ghi index, rule ID, status và thời gian.

### 16.2. Priority-based rules

Rule có priority. Cần ghi priority hiệu lực và cách engine giải quyết khi nhiều rule cùng match.

### 16.3. First-match decision table

Trong bảng quyết định, engine có thể chọn dòng đầu tiên match. Audit nên ghi row ID được chọn và các row trước đó đã không match hay bị bỏ qua.

### 16.4. Unique-hit và collect

Với policy unique-hit, nhiều rule cùng match có thể là lỗi cấu hình hoặc trạng thái không mong muốn. Với collect, nhiều rule có thể đóng góp kết quả. Audit cần ghi policy hit strategy và tập kết quả.

### 16.5. Agenda-based engine

Engine có agenda có thể kích hoạt rule theo conflict resolution strategy. Trace cần lưu activation identity hoặc đủ metadata để biết vì sao rule được chọn tiếp theo.

### 16.6. Rule chain và sub-decision

Một decision có thể gọi sub-decision. Audit nên tạo quan hệ parent-child hoặc trace span để người đọc theo được cây quyết định.

## 17. Kiểm toán thay đổi rule và policy

Audit của từng quyết định cần được nối với lịch sử thay đổi policy.

### 17.1. Policy change event

Một event thay đổi policy có thể ghi:

- Policy ID và version mới.
- Người tạo và người phê duyệt.
- Nội dung hoặc artifact hash.
- Lý do thay đổi.
- Thời điểm publish và activate.
- Môi trường triển khai.
- Kết quả validation hoặc approval workflow.

### 17.2. Tách change audit và decision audit

Decision audit trả lời “một quyết định đã được tạo ra thế nào?”. Change audit trả lời “ai đã thay đổi policy, thay đổi gì và khi nào?”. Hai luồng liên kết qua policy ID/version nhưng phục vụ câu hỏi khác nhau.

### 17.3. Approval workflow

Policy có ảnh hưởng lớn có thể cần người tạo và người phê duyệt khác nhau. Audit nên lưu approval record và artifact hash đã được phê duyệt để bảo đảm artifact deploy chính là artifact đã review.

### 17.4. Rollback policy

Khi rollback, không xóa lịch sử version mới. Ghi deployment event cho biết môi trường quay về version nào, ai thực hiện và lý do.

### 17.5. So sánh kết quả giữa hai version

Có thể chạy shadow evaluation: cùng input được đánh giá bởi policy đang hoạt động và policy candidate. Chỉ một kết quả được dùng để thực hiện action; kết quả còn lại phục vụ so sánh và cần được đánh dấu là simulation.

## 18. Truy vấn và báo cáo audit

Audit record cần có khả năng truy vấn theo các định danh và tiêu chí nghiệp vụ.

Các truy vấn thường gặp:

- Tìm decision theo decision ID hoặc case ID.
- Tìm các quyết định trong khoảng thời gian.
- Lọc theo outcome hoặc reason code.
- Tìm decision theo policy version.
- Tìm các quyết định có rule cụ thể match.
- Tìm decision có rule evaluation failed.
- So sánh tỷ lệ outcome giữa hai policy version.
- Tìm các quyết định được thực hiện bởi một actor.

### 18.1. Index

Index có thể đặt trên decision ID, case ID, timestamp, policy ID/version, outcome và reason code. Không nên index mọi field vì làm tăng chi phí ghi và lưu trữ.

### 18.2. Partition

Partition theo thời gian hoặc tenant có thể giúp retention và truy vấn. Cần tránh partition strategy khiến một tenant lớn tạo hot partition.

### 18.3. Report aggregate

Báo cáo tổng hợp có thể cho biết tỷ lệ approve/reject theo policy version hoặc reason code. Aggregate cần giữ định nghĩa metric ổn định để so sánh theo thời gian.

### 18.4. Audit export

Export cần ghi ai yêu cầu, phạm vi dữ liệu, thời điểm và định dạng. File export cũng cần được bảo vệ và có retention riêng.

### 18.5. Không dùng audit store như analytics warehouse duy nhất

Audit store ưu tiên độ tin cậy, toàn vẹn và truy vết. Analytics warehouse ưu tiên phân tích và tổng hợp. Có thể sao chép dữ liệu đã được kiểm soát sang warehouse, nhưng cần giữ nguồn gốc và không làm mất liên kết với audit record gốc.

## 19. Quan sát và cảnh báo

Audit data có thể hỗ trợ phát hiện thay đổi bất thường trong hành vi decision engine.

Ví dụ metric:

- Số quyết định theo phút.
- Tỷ lệ approve/reject.
- Tỷ lệ từng reason code.
- Số rule match.
- Số lần rule evaluation failed.
- Số quyết định thiếu audit event.
- Độ trễ ghi audit.
- Tỷ lệ event bị retry hoặc dead-letter.

### 19.1. Baseline

Một policy thay đổi có thể làm tỷ lệ reject tăng mạnh. So sánh với baseline giúp phát hiện thay đổi bất thường.

### 19.2. Alert

Alert có thể kích hoạt khi tỷ lệ lỗi, tỷ lệ một reason code hoặc độ trễ audit vượt ngưỡng. Ngưỡng cần được đặt theo nghiệp vụ và lưu cấu hình alert riêng.

### 19.3. Audit gap

Nếu decision count lớn hơn audit record count, có thể tồn tại quyết định thiếu dấu vết. Cần metric reconciliation để phát hiện khoảng trống thay vì chỉ kiểm tra log ghi thành công.

### 19.4. Không để metric thay thế record

Metric tổng hợp không thể thay thế audit record của từng quyết định. Nó không đủ để giải thích một case cụ thể.

## 20. Xử lý lỗi trong audit pipeline

Audit pipeline cũng có thể gặp lỗi: schema không hợp lệ, storage timeout, queue đầy, permission bị từ chối hoặc checksum mismatch.

### 20.1. Retry

Retry cần giới hạn, backoff và jitter để tránh tạo tải tăng đột biến. Event retry phải giữ cùng logical event ID.

### 20.2. Dead-letter queue

Event không thể xử lý sau số lần retry có thể được chuyển vào dead-letter queue. Record cần giữ nguyên payload hoặc reference an toàn, lỗi, số lần thử và thời điểm.

### 20.3. Reconciliation

Định kỳ so sánh decision ledger với audit ledger hoặc outbox để tìm bản ghi thiếu, trùng hoặc chưa được chuyển tiếp.

### 20.4. Corrupt record

Nếu checksum hoặc signature không hợp lệ, không nên tự sửa record. Đánh dấu integrity failure, cách ly và điều tra theo quy trình.

### 20.5. Backpressure

Khi audit consumer chậm, queue có thể tăng. Hệ thống cần giới hạn dung lượng, cảnh báo và policy khi đạt ngưỡng. Với decision bắt buộc audit, cần xác định liệu có dừng nhận quyết định mới hay ghi vào durable buffer.

## 21. Kiểm thử khả năng kiểm toán

Kiểm thử audit tập trung vào việc record có đầy đủ và đúng ngữ nghĩa, không chỉ kiểm tra decision outcome.

### 21.1. Trace completeness

Với mỗi decision, xác nhận có decision ID, model version, outcome và những trace field được audit policy yêu cầu.

### 21.2. Matched và not-matched rules

Tạo input làm rule match và input làm rule không match. Xác nhận status trong trace phản ánh đúng kết quả.

### 21.3. Skipped rule

Tạo tình huống early exit hoặc short-circuit. Xác nhận rule chưa được đánh giá được ghi là skipped thay vì not matched.

### 21.4. Version provenance

Chạy cùng input với hai policy version khác nhau. Xác nhận audit record lưu đúng version và artifact hash.

### 21.5. Input immutability

Sau khi decision hoàn tất, cập nhật hồ sơ gốc. Kiểm tra snapshot hoặc revision reference vẫn tái hiện được input lịch sử.

### 21.6. Replay

Chạy replay ở chế độ không side effect với cùng input, policy và dependency snapshot. So sánh outcome và trace theo quy tắc deterministic đã công bố.

### 21.7. Integrity

Thử sửa một record hoặc thay đổi thứ tự record. Xác nhận checksum, hash chain hoặc signature verification phát hiện thay đổi.

### 21.8. Privacy

Kiểm tra field nhạy cảm không xuất hiện trong log, explanation hoặc export cho role không được phép.

### 21.9. Failure handling

Mô phỏng audit store timeout, queue đầy, consumer retry và duplicate event. Xác nhận decision/audit consistency theo policy.

## 22. Ví dụ end-to-end: quyết định duyệt đơn

Giả sử decision model:

~~~text
decision OrderApproval version "3.7.2" {
    input {
        amount: Money
        customerRisk: RiskLevel
        country: Country
        customerAgeDays: Integer
    }

    rule BlockHighRisk priority 100 {
        when customerRisk == HIGH
        then reject("CUSTOMER_HIGH_RISK")
    }

    rule ReviewNewCustomer priority 80 {
        when customerAgeDays < 30
        then requireManualReview("NEW_CUSTOMER")
    }

    rule ReviewHighValue priority 60 {
        when amount > 10000
        then requireManualReview("HIGH_VALUE")
    }

    default approve("STANDARD_APPROVAL")
}
~~~

Input:

~~~json
{
  "amount": 12500,
  "customerRisk": "HIGH",
  "country": "VN",
  "customerAgeDays": 12
}
~~~

Giả sử engine dừng khi rule terminal BlockHighRisk match. Trace có thể là:

~~~json
{
  "decisionId": "dec-1042",
  "policy": {
    "id": "OrderApproval",
    "version": "3.7.2",
    "artifactHash": "sha256:abc..."
  },
  "ruleTrace": [
    {
      "ruleId": "BlockHighRisk",
      "priority": 100,
      "status": "MATCHED",
      "evidence": {
        "customerRisk": "HIGH",
        "expected": "HIGH"
      }
    },
    {
      "ruleId": "ReviewNewCustomer",
      "priority": 80,
      "status": "SKIPPED",
      "skipReason": "TERMINAL_DECISION"
    },
    {
      "ruleId": "ReviewHighValue",
      "priority": 60,
      "status": "SKIPPED",
      "skipReason": "TERMINAL_DECISION"
    }
  ],
  "outcome": {
    "status": "REJECTED",
    "reasonCodes": ["CUSTOMER_HIGH_RISK"]
  }
}
~~~

Explanation cho nhân viên hỗ trợ:

~~~text
Đơn hàng APP-1042 bị từ chối.

Lý do:
Hồ sơ được phân loại rủi ro HIGH.

Policy:
OrderApproval version 3.7.2

Rule quyết định:
BlockHighRisk

Các rule manual review phía sau không được đánh giá vì
engine đã kết thúc theo terminal decision.
~~~

Điểm quan trọng là ReviewNewCustomer và ReviewHighValue được ghi là skipped. Không thể kết luận chúng không match vì engine đã dừng trước khi đánh giá.

## 23. Ví dụ audit cho bảng quyết định

Một decision table có thể phân loại hồ sơ:

| Row ID | Risk | Amount | Outcome |
|---|---|---:|---|
| R-01 | HIGH | Any | REJECT |
| R-02 | MEDIUM | Greater than 10000 | REVIEW |
| R-03 | LOW | Any | APPROVE |

Nếu chiến lược là first-match, audit nên ghi table ID và version, row ID được chọn, những row được đánh giá trước đó và kết quả, những row bị bỏ qua sau khi đã có match, input columns có liên quan, outcome và reason code.

Ví dụ:

~~~json
{
  "decisionTable": "CreditRouting",
  "version": "5",
  "hitPolicy": "FIRST",
  "matchedRow": "R-02",
  "evaluations": [
    {"row": "R-01", "status": "NOT_MATCHED"},
    {"row": "R-02", "status": "MATCHED"},
    {"row": "R-03", "status": "SKIPPED"}
  ],
  "outcome": "REVIEW"
}
~~~

Nếu engine đánh giá tất cả row rồi áp dụng hit policy khác, trace cần phản ánh đúng semantics đó.

## 24. Governance và trách nhiệm giải trình

Kiểm toán quyết định không chỉ là vấn đề kỹ thuật. Nó liên quan đến quy trình quản trị policy và trách nhiệm của tổ chức.

### 24.1. Ownership

Mỗi decision model nên có owner chịu trách nhiệm về semantics, tài liệu, test và thay đổi policy.

### 24.2. Change approval

Policy có ảnh hưởng lớn có thể cần review và phê duyệt trước khi activate. Audit cần liên kết approval với đúng artifact hash.

### 24.3. Separation of duties

Người tạo rule và người phê duyệt có thể cần là hai vai trò riêng. Quyền deploy policy cũng nên được kiểm soát.

### 24.4. Explainability review

Khi thiết kế rule, cần xem liệu outcome có reason code và evidence đủ để giải thích hay không. Rule chỉ trả về một boolean không phải lúc nào cũng cung cấp đủ ngữ cảnh cho audit.

### 24.5. Quy trình khiếu nại

Nếu người dùng yêu cầu xem xét quyết định, hệ thống cần tìm historical decision, giải thích dựa trên record gốc và ghi nhận việc review như một event mới. Không sửa trực tiếp lịch sử.

## 25. Các nguyên tắc thiết kế

Một hệ thống decision audit đáng tin cậy thường tuân theo những nguyên tắc sau:

1. Mỗi lần đánh giá có decision ID riêng.
2. Ghi nhận chính xác policy và dependency version đã thực thi.
3. Giữ input snapshot hoặc reference bất biến đủ để giải thích.
4. Phân biệt matched, not matched, skipped và failed.
5. Ghi evidence cho các rule có ảnh hưởng đến outcome.
6. Lưu outcome và reason code ổn định.
7. Tách decision audit khỏi operational log và policy change audit.
8. Bảo vệ record bằng access control và cơ chế phát hiện sửa đổi.
9. Giới hạn dữ liệu nhạy cảm và định nghĩa retention.
10. Hỗ trợ replay không side effect khi có yêu cầu.
11. Xử lý duplicate, retry và failure trong hệ thống phân tán.
12. Duy trì khả năng đọc audit schema cũ.

## 26. Những sai lầm thường gặp

**Chỉ lưu outcome.** Một giá trị approve/reject không đủ để giải thích vì sao quyết định được tạo ra.

**Không lưu policy version.** Khi rule thay đổi, không thể xác định quyết định lịch sử dùng policy nào.

**Dùng input hiện tại để giải thích quyết định cũ.** Hồ sơ có thể đã được cập nhật sau quyết định; cần snapshot hoặc immutable revision.

**Gộp skipped với not matched.** Một rule chưa được đánh giá không thể được xem là đã đánh giá và cho kết quả false.

**Không lưu dependency provenance.** Cùng decision model có thể thay đổi kết quả khi package hoặc bảng quyết định được cập nhật.

**Tạo explanation bằng suy đoán.** Reason phải dựa trên execution trace và evidence thực tế.

**Ghi toàn bộ dữ liệu nhạy cảm.** Audit có thể trở thành một bản sao dữ liệu cá nhân hoặc secret không cần thiết.

**Cho phép sửa record lịch sử.** Correction nên được ghi thành event mới có liên kết và lý do.

**Replay có side effect.** Chạy lại quyết định không được tự động gửi lệnh hoặc thực hiện giao dịch lần nữa.

**Giả định event chỉ được gửi một lần.** Retry và duplicate là tình huống bình thường trong hệ thống phân tán.

**Bỏ qua lỗi ghi audit.** Quyết định quan trọng có thể hoàn tất mà không có dấu vết nếu không có policy xử lý failure.

**Dùng metric thay audit record.** Tỷ lệ approve/reject không thể giải thích một hồ sơ cụ thể.

## 27. Ghi nhớ

- Kiểm toán quyết định ghi lại cách một decision được tạo ra, không chỉ kết quả cuối cùng.
- Audit record thường gồm identity, timestamp, actor, input, policy provenance, rule trace, evidence, outcome và correlation data.
- Input snapshot hoặc immutable reference giúp giải thích quyết định sau khi dữ liệu nguồn thay đổi.
- Policy version, artifact hash và dependency version xác định chính xác logic đã được thực thi.
- Matched, not matched, skipped và failed là các trạng thái khác nhau.
- Evidence và reason code giúp tạo explanation có căn cứ.
- Decision audit, operational logging và policy change audit phục vụ các mục đích khác nhau nhưng có thể liên kết.
- Append-only storage, hash chain, signature và access control hỗ trợ tính toàn vẹn.
- Data minimization, masking, encryption, role-based access và retention bảo vệ dữ liệu audit.
- Replay lịch sử khác re-evaluation bằng policy hiện tại; replay cần input và dependency history phù hợp.
- Hệ thống phân tán cần correlation ID, idempotency, outbox, retry và reconciliation.
- Audit schema cần versioning để đọc được record cũ trong thời gian dài.

## 28. Câu hỏi tự kiểm tra

1. Kiểm toán quyết định là gì và khác operational logging ở điểm nào?
2. Vì sao chỉ lưu outcome approve hoặc reject là chưa đủ?
3. Một decision audit record nên có những nhóm thông tin nào?
4. So sánh input snapshot và input reference. Khi nào nên dùng kết hợp?
5. Vì sao cần lưu policy version, artifact hash và dependency version?
6. Phân biệt matched, not matched, skipped và failed trong rule trace.
7. Evidence khác reason code như thế nào?
8. Làm thế nào tạo explanation dựa trên dữ liệu thực tế thay vì suy đoán?
9. Decision audit khác policy change audit ở câu hỏi nào?
10. Append-only storage, hash chain và digital signature hỗ trợ tính toàn vẹn ra sao?
11. Những nguyên tắc nào giúp bảo vệ dữ liệu cá nhân và secret trong audit?
12. Replay quyết định lịch sử khác re-evaluation bằng policy mới như thế nào?
13. Vì sao replay cần chế độ không side effect?
14. Làm thế nào xử lý duplicate event khi ghi audit trong hệ thống phân tán?
15. Transactional outbox giải quyết vấn đề nhất quán giữa decision và audit ra sao?
16. Audit cần ghi gì khi một rule engine dừng sớm sau terminal rule?
17. Hãy thiết kế trace cho một decision table sử dụng first-match hit policy.
18. Nếu audit store không khả dụng, những policy fail-closed hoặc durable-buffer có ưu nhược điểm gì?
