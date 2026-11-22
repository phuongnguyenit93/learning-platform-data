# Giải thích kết quả

Trong một hệ thống sử dụng ngôn ngữ miền đặc thù cho luật và quyết định (Rule and Decision DSL), engine thường nhận dữ liệu đầu vào, đánh giá một tập điều kiện, áp dụng quy tắc ưu tiên và trả về quyết định. Kết quả có thể là phê duyệt hay từ chối một giao dịch, phân loại một hồ sơ, xác định mức phí, chọn một workflow hoặc đưa ra hành động tiếp theo. Tuy nhiên, chỉ trả về một giá trị như `APPROVED`, `REJECTED` hoặc `RISK_HIGH` thường chưa đủ để người dùng và người vận hành hiểu điều gì đã xảy ra.

**Giải thích kết quả** (*result explanation* hoặc *decision explainability*) là khả năng trình bày có cấu trúc cách engine đi đến kết quả: dữ kiện nào được sử dụng, luật nào được đánh giá, điều kiện nào đúng hoặc sai, quy tắc nào được kích hoạt, cách xử lý xung đột diễn ra ra sao và yếu tố nào quyết định kết quả cuối cùng. Giải thích tốt giúp người dùng hiểu quyết định, chuyên gia nghiệp vụ kiểm tra chính sách, developer gỡ lỗi DSL và auditor truy vết một lần thực thi cụ thể.

Ví dụ một DSL xét duyệt đơn hàng:

~~~text
decision OrderApproval(order) {
    rule HighValueOrder priority 100 {
        when order.total >= 1000;
        then requireManagerApproval;
    }

    rule TrustedCustomer priority 80 {
        when order.customer.status == TRUSTED;
        then approve;
    }

    rule FraudAlert priority 200 {
        when order.riskScore >= 90;
        then reject;
    }
}
~~~

Giả sử đầu vào có tổng tiền 1.500, khách hàng thuộc nhóm `TRUSTED` và điểm rủi ro là 25. Engine có thể kích hoạt hai rule đầu, nhưng kết quả cuối cùng phụ thuộc semantics của decision DSL: các rule có được áp dụng đồng thời không, priority được xử lý thế nào, `requireManagerApproval` có dừng quá trình không và `approve` có ghi đè trạng thái trước đó không. Một lời giải thích hữu ích cần thể hiện chính xác đường đi đó thay vì chỉ nói “đơn hàng cần phê duyệt”.

Giải thích kết quả không chỉ là log văn bản. Nó là dữ liệu có cấu trúc gắn với một execution cụ thể, có thể được hiển thị thành câu chữ, bảng, timeline hoặc trace. Cần phân biệt giải thích với kết quả nghiệp vụ, diagnostic của chương trình, log kỹ thuật và audit record; các loại dữ liệu này liên quan nhưng phục vụ mục đích khác nhau.

## 1. Giải thích kết quả là gì?

Trong DSL luật và quyết định, engine thực hiện một quá trình đánh giá. Quá trình này có thể gồm:

- Nhận và chuẩn hóa input.
- Tạo tập facts hoặc context.
- Xác định những rule có thể áp dụng.
- Đánh giá từng điều kiện.
- Kích hoạt rule phù hợp.
- Giải quyết xung đột giữa các rule.
- Thực hiện action hoặc tạo candidate decision.
- Kết hợp kết quả trung gian thành kết quả cuối.

Giải thích kết quả mô tả những bước có ý nghĩa trong quá trình đó và liên kết chúng với kết quả cuối cùng.

Một explanation record có thể chứa:

~~~text
DecisionExplanation
  executionId
  decisionId
  decisionVersion
  outcome
  inputSummary
  evaluatedRules[]
  matchedRules[]
  skippedRules[]
  factsUsed[]
  intermediateResults[]
  conflictResolution
  contributingReasons[]
  warnings[]
  traceReference
~~~

Đây là mô hình khái niệm. Một hệ thống có thể lưu các phần chi tiết ở nhiều record hoặc event khác nhau, nhưng cần giữ được mối liên kết với execution và version chương trình.

### Explanation trả lời những câu hỏi nào?

Một người đọc có thể cần biết:

- Quyết định cuối cùng là gì?
- Những luật nào được đánh giá?
- Luật nào khớp và luật nào không khớp?
- Điều kiện nào làm một luật khớp hoặc không khớp?
- Dữ liệu nào được dùng để đánh giá?
- Có luật nào bị bỏ qua vì điều kiện, scope hoặc policy không?
- Nếu nhiều luật cùng khớp, engine chọn hoặc kết hợp chúng thế nào?
- Action nào được thực hiện và kết quả của action là gì?
- Có fallback, default hoặc manual review nào được áp dụng không?
- Kết quả được tạo bởi phiên bản DSL và policy nào?
- Có dữ liệu nào không thể đánh giá hoặc bị thiếu không?

Không phải mọi người dùng đều cần tất cả chi tiết. Người dùng nghiệp vụ thường cần lý do chính và bước tiếp theo; developer cần trace chi tiết; auditor cần provenance, version và bằng chứng có thể kiểm chứng.

## 2. Phân biệt explanation, result, diagnostic, log và audit

Các khái niệm này thường bị dùng lẫn nhau, nhưng nên có ranh giới rõ.

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Decision result | Trả kết quả nghiệp vụ cho caller. | `REQUIRES_REVIEW`. |
| Explanation | Diễn giải vì sao kết quả được tạo ra. | `HighValueOrder` khớp vì tổng tiền là 1.500. |
| Diagnostic | Báo vấn đề trong chương trình hoặc dữ liệu. | Rule tham chiếu field không tồn tại. |
| Runtime log | Ghi sự kiện vận hành và lỗi kỹ thuật. | Action `loadCustomer` mất 42 ms. |
| Audit record | Ghi hoạt động cần truy cứu và trách nhiệm. | Principal A chạy decision version 12 lúc... |
| Trace | Chuỗi sự kiện theo thời gian hoặc quan hệ nhân quả. | Evaluate condition → activate rule → resolve conflict. |

### Result không thay thế explanation

Một API có thể trả `REQUIRES_REVIEW` nhưng không cho biết lý do. Nếu caller cần hiển thị hoặc hỗ trợ người dùng, cần một explanation contract riêng hoặc một response chứa cả outcome và explanation reference.

### Explanation không thay thế diagnostic

Một rule có thể không được đánh giá do chương trình lỗi, thiếu dữ liệu hoặc không resolve được symbol. Đây có thể là execution diagnostic, không nên biến thành một lý do nghiệp vụ giả như “điều kiện không khớp”.

### Log không nhất thiết là explanation

Log thường phản ánh chi tiết triển khai như thread, SQL, retry và latency. Nó có thể quá kỹ thuật, khó tổng hợp và chứa dữ liệu không phù hợp để hiển thị cho người dùng cuối.

### Audit không nhất thiết lưu mọi biểu thức

Audit tập trung vào ai, cái gì, khi nào, trên dữ liệu và phiên bản nào, cùng bằng chứng cần thiết. Explanation có thể được tái tạo từ trace, nhưng nếu dữ liệu đầu vào thay đổi hoặc policy không còn tồn tại, việc tái tạo có thể không chính xác. Hệ thống có yêu cầu audit cần lưu snapshot hoặc bằng chứng đủ để xác minh kết quả lịch sử.

## 3. Vì sao DSL luật và quyết định cần giải thích kết quả?

### Tạo niềm tin vào quyết định

Khi engine đưa ra quyết định có ảnh hưởng đến khách hàng, nhân viên hoặc quy trình, người nhận cần biết cơ sở chính. Một kết quả không có lý do có thể khó được chấp nhận, đặc biệt khi kết quả bất lợi.

### Hỗ trợ chuyên gia nghiệp vụ

Chuyên gia có thể kiểm tra một rule có phản ánh đúng policy không, điều kiện có quá rộng hay quá hẹp không và priority có dẫn đến kết quả ngoài dự kiến không.

### Gỡ lỗi rule

Nếu một hồ sơ bị từ chối ngoài dự kiến, trace có thể chỉ ra rule nào đã match, fact nào có giá trị khác mong đợi hoặc rule ưu tiên cao hơn đã thắng.

### Quản lý thay đổi policy

Khi một phiên bản DSL mới tạo kết quả khác, explanation có thể giúp so sánh hai execution và xác định rule hoặc điều kiện nào làm kết quả thay đổi.

### Tuân thủ và kiểm toán

Một số lĩnh vực cần chứng minh quyết định được tạo theo policy đã phê duyệt và dữ liệu nào được dùng. Explanation có cấu trúc giúp cung cấp bằng chứng có thể truy vết.

### Hỗ trợ vận hành và khiếu nại

Support team có thể giải thích kết quả cho người dùng mà không cần đọc source code hoặc log nội bộ. Với quy trình có khiếu nại, explanation giúp xác định điểm cần xem xét lại.

### Phát hiện bias và lỗi dữ liệu

Việc xem các feature/fact có ảnh hưởng đến quyết định giúp nhóm quản trị phát hiện dữ liệu sai, policy bất hợp lý hoặc trường hợp một yếu tố được dùng ngoài ý định. Explanation hỗ trợ kiểm tra nhưng tự nó không chứng minh hệ thống công bằng hay không có bias.

## 4. Những tầng giải thích trong một rule engine

Một hệ thống có thể tạo explanation ở nhiều mức chi tiết.

### Mức quyết định

Hiển thị outcome cuối và một vài lý do chính:

~~~text
Kết quả: Cần quản lý phê duyệt
Lý do chính: Giá trị đơn hàng vượt ngưỡng 1.000.
~~~

### Mức rule

Cho biết các rule được đánh giá, match hoặc không match:

~~~text
HighValueOrder: MATCHED
TrustedCustomer: MATCHED
FraudAlert: NOT_MATCHED
~~~

### Mức điều kiện

Hiển thị từng predicate và giá trị hai vế:

~~~text
order.total >= 1000
actual: 1500 >= 1000
result: true
~~~

### Mức fact và dữ liệu

Cho biết giá trị đã được lấy từ đâu, có được biến đổi hay không, thời điểm và độ tin cậy của nguồn.

### Mức execution trace

Hiển thị thứ tự đánh giá, activation, action, conflict resolution, retry và các bước kết thúc.

### Mức kỹ thuật

Bao gồm rule node ID, source location, symbol ID, evaluator operation, correlation ID và metadata cần cho developer.

Các tầng này có thể được yêu cầu độc lập. Không nên luôn thu thập và trả toàn bộ trace chi tiết cho mọi request nếu chi phí hoặc dữ liệu nhạy cảm không cho phép.

## 5. Mô hình rule evaluation

Để giải thích kết quả, trước hết cần mô hình hóa cách engine đánh giá rule.

Một rule thường gồm:

~~~text
Rule
  id
  name
  scope
  priority
  condition
  action
  activationPolicy
  version
~~~

Engine có thể thực hiện các bước:

1. Xác định rule thuộc decision hoặc scope hiện tại.
2. Kiểm tra rule có enabled và hợp lệ không.
3. Chuẩn bị facts và context cần thiết.
4. Đánh giá condition.
5. Ghi kết quả match/no-match hoặc evaluation error.
6. Nếu match, tạo activation hoặc candidate result.
7. Đưa activation vào agenda hoặc conflict set nếu engine dùng cơ chế đó.
8. Chọn activation theo strategy.
9. Thực thi action hoặc cập nhật decision state.
10. Xác định điều kiện dừng và kết quả cuối.

### Match và execute là hai trạng thái khác nhau

Một rule có thể match nhưng action chưa được thực thi vì activation bị loại, bị ưu tiên thấp hơn, bị hủy hoặc decision đã dừng. Explanation phải phân biệt `MATCHED` với `FIRED`/`EXECUTED`.

### Rule không match

Một rule không match có thể vì condition trả false, rule không nằm trong scope, thiếu fact, rule bị disable hoặc không được đánh giá do short-circuit. Những nguyên nhân này khác nhau và không nên gộp vào một trạng thái `NOT_MATCHED` mơ hồ.

### Evaluation error

Nếu biểu thức lỗi, ví dụ chia cho 0 hoặc reference không hợp lệ, đó là `EVALUATION_ERROR`, không phải false. Nếu engine dùng three-valued logic hoặc unknown value, semantics cần được ghi rõ.

## 6. Mô hình kết quả đánh giá rule

Một evaluation record có thể chứa:

~~~text
RuleEvaluation
  ruleId
  ruleVersion
  sourceLocation
  status
  conditionResult
  evaluatedAt
  factsReferenced[]
  conditionTrace
  activationId
  skipReason
  error
~~~

Các trạng thái gợi ý:

| Status | Ý nghĩa |
|---|---|
| `NOT_EVALUATED` | Rule chưa được đánh giá. |
| `SKIPPED` | Rule bị bỏ qua do scope, disabled, guard hoặc short-circuit. |
| `MATCHED` | Điều kiện trả true. |
| `NOT_MATCHED` | Điều kiện được đánh giá và trả false. |
| `UNKNOWN` | Không đủ dữ liệu để kết luận theo semantics của DSL. |
| `EVALUATION_ERROR` | Có lỗi khi đánh giá điều kiện. |
| `ACTIVATED` | Rule match và tạo activation/candidate. |
| `FIRED` | Action của rule đã được thực thi. |
| `CANCELLED` | Activation hoặc rule execution bị hủy. |
| `SUPPRESSED` | Kết quả bị policy hoặc conflict strategy loại khỏi tác động cuối. |

Tên trạng thái thực tế có thể khác. Điều quan trọng là không nhập nhằng trạng thái điều kiện, trạng thái activation và trạng thái action.

### Vì sao cần skip reason?

Nếu rule `FraudAlert` không được đánh giá vì decision đã dừng ở bước trước, không thể kết luận rằng hồ sơ không có dấu hiệu gian lận. Explanation nên nói rõ rule chưa được chạy do execution policy, thay vì hiển thị “FraudAlert không match”.

## 7. Giải thích điều kiện và biểu thức

Một condition có thể là biểu thức đơn giản hoặc tổ hợp nhiều predicate.

~~~text
when order.total >= 1000
  and customer.status == TRUSTED
  and order.country in allowedCountries;
~~~

Explanation ở mức điều kiện có thể biểu diễn cây đánh giá:

~~~text
AND
├── order.total >= 1000
│   └── 1500 >= 1000 -> true
├── customer.status == TRUSTED
│   └── TRUSTED == TRUSTED -> true
└── order.country in allowedCountries
    └── VN in [VN, SG, TH] -> true
~~~

### Short-circuit evaluation

Với `A and B`, nếu `A` false và DSL quy định short-circuit, engine có thể không đánh giá `B`. Explanation cần hiển thị `B` là `NOT_EVALUATED` do short-circuit, không phải `false`.

Tương tự, với `A or B`, nếu `A` true, `B` có thể không được đánh giá.

### Nested conditions

Điều kiện có thể lồng `not`, `and`, `or`, function call và property access. Trace nên giữ cấu trúc cây hoặc quan hệ cha–con để người đọc hiểu nguyên nhân tổng hợp.

### Function trong condition

Nếu condition gọi function như `isTrusted(customer)`, explanation có thể hiển thị function result và các input liên quan. Nếu function đọc hệ thống bên ngoài, cần lưu nguồn dữ liệu hoặc action trace thích hợp.

### Side effects trong expression

Tốt nhất nên giữ expression thuần và action riêng biệt. Nếu function trong condition có tác dụng phụ, việc đánh giá lại để giải thích có thể tạo hành vi khác. Explanation nên lấy từ execution trace gốc thay vì chạy lại biểu thức.

### Unknown và null

Nếu dữ liệu thiếu, null hoặc không xác định, DSL cần quy định condition trả false, unknown hay error. Explanation phải giữ đúng trạng thái này. Không được biến “không có dữ liệu” thành “điều kiện không thỏa” nếu semantics phân biệt chúng.

## 8. Facts và nguồn dữ liệu được sử dụng

Rule engine thường đánh giá rule trên facts, input hoặc context. Explanation cần chỉ ra dữ liệu nào thực sự ảnh hưởng đến kết quả.

Một fact record có thể gồm:

~~~text
FactReference
  factId
  name
  valueSummary
  source
  observedAt
  version
  confidence
  sensitivity
~~~

### Input trực tiếp

Giá trị do caller truyền vào, ví dụ tổng tiền, loại khách hàng hoặc ngày giao dịch.

### Dữ liệu truy vấn

Giá trị được lấy từ database, service hoặc provider. Explanation cần ghi nguồn và thời điểm quan sát để người xem hiểu dữ liệu có thể đã thay đổi sau execution.

### Derived fact

Một fact có thể được tính từ các fact khác, ví dụ `customerRisk = combine(history, velocity, signals)`. Explanation nên thể hiện nguồn gốc và phép biến đổi ở mức phù hợp.

### Fact được suy ra từ rule

Một rule có thể tạo fact mới, rồi fact đó kích hoạt rule khác. Trace cần liên kết fact được tạo với rule/action đã tạo ra nó.

### Data lineage

Lineage mô tả nguồn gốc và đường biến đổi của dữ liệu. Nó giúp trả lời một kết quả phụ thuộc vào nguồn nào, qua phép tính nào và bằng phiên bản dữ liệu nào.

### Không phải mọi input đều là reason

Một request có thể chứa hàng trăm field nhưng chỉ vài field ảnh hưởng đến quyết định. Explanation nên ưu tiên facts thực sự được tham chiếu trong các điều kiện hoặc action đóng góp, tránh hiển thị toàn bộ payload.

## 9. Giải thích kết quả khi nhiều rule cùng match

Trong rule engine, nhiều rule có thể cùng match. Kết quả phụ thuộc conflict resolution strategy và semantics của DSL.

### Priority

Rule có priority cao hơn có thể được thực thi trước. Cần xác định số lớn hơn hay nhỏ hơn có ưu tiên cao hơn, cách xử lý bằng điểm và hành vi khi bằng priority.

### Salience hoặc agenda ordering

Một số engine tạo agenda chứa các activation và chọn activation theo salience, recency, specificity hoặc chiến lược khác. Explanation nên ghi tiêu chí nào quyết định thứ tự.

### First match wins

Engine có thể dừng sau rule đầu tiên khớp theo thứ tự được xác định. Trong trường hợp này, các rule phía sau có thể `NOT_EVALUATED`, không phải `NOT_MATCHED`.

### All matching rules

Engine có thể chạy mọi rule khớp rồi kết hợp action/result. Cần quy định cách merge kết quả, xử lý action conflict và thứ tự thực thi.

### Mutual exclusion

Một nhóm rule có thể được định nghĩa loại trừ lẫn nhau. Nếu nhiều rule cùng match, engine cần báo ambiguity hoặc áp dụng tie-breaker đã công bố.

### Rule groups và activation groups

Một group có thể giới hạn số rule được firing hoặc chỉ cho một rule trong nhóm chạy. Explanation cần thể hiện group membership và lý do một activation bị hủy/suppressed.

### Conflict resolution record

Ví dụ:

~~~text
ConflictResolution
  candidates:
    - HighValueOrder (priority 100)
    - TrustedCustomer (priority 80)
  strategy: PRIORITY_THEN_SOURCE_ORDER
  selected: HighValueOrder
  suppressed:
    - TrustedCustomer: decision already requires review
~~~

Record này giúp phân biệt rule nào match với rule nào thực sự đóng góp vào kết quả.

## 10. Giải thích kết quả trong decision table

Decision table thường có hàng là rule, cột là input condition và output action/result. Explanation cần chỉ ra hàng nào match và cột nào làm hàng đó match.

Ví dụ:

| Rule | Amount | Customer | Risk | Decision |
|---|---:|---|---:|---|
| R1 | `>= 1000` | Any | Any | Review |
| R2 | Any | Trusted | `< 50` | Approve |
| R3 | Any | Any | `>= 90` | Reject |

Input:

~~~text
amount = 1500
customer = Trusted
risk = 25
~~~

R1 và R2 cùng match, R3 không match. Nếu table dùng `FIRST` hit policy theo thứ tự dòng, R1 có thể quyết định kết quả. Nếu dùng `COLLECT`, engine có thể trả nhiều output hoặc cần aggregation. Explanation phải ghi rõ hit policy.

### Hit policies

Các decision table thường có những chiến lược như:

- **Unique:** tối đa một rule được match.
- **Any:** nhiều rule có thể match nhưng output phải tương đương theo quy tắc.
- **First:** chọn rule đầu tiên theo thứ tự bảng.
- **Priority:** chọn output có mức ưu tiên cao nhất.
- **Collect:** thu thập kết quả từ mọi rule match.
- **Rule order:** trả kết quả theo thứ tự rule.

Tên và chi tiết hit policy phụ thuộc DSL/engine. Explanation cần hiển thị policy thực tế được áp dụng, không chỉ liệt kê các row match.

### Aggregation

Với collect, engine có thể sum, min, max, count hoặc union các output. Explanation nên chỉ ra các output thành phần và phép tổng hợp.

Ví dụ:

~~~text
Matched discounts: [5, 10, 3]
Aggregation: SUM
Final discount: 18
~~~

## 11. Kết quả tổng hợp và decision state

Một decision có thể được xây dựng qua nhiều bước, không chỉ bằng một rule.

Ví dụ trạng thái:

~~~text
PENDING -> VALIDATED -> APPROVED -> FULFILLMENT_READY
~~~

Engine có thể duy trì state accumulator hoặc decision context. Explanation cần cho biết trạng thái trước/sau, rule hoặc action gây chuyển trạng thái và điều kiện chuyển đổi.

### Accumulator

Nhiều rule có thể cập nhật cùng một accumulator như score, set flags hoặc list reasons. Cần ghi lại mỗi contribution và phép tính để có thể giải thích tổng cuối.

### Score aggregation

Ví dụ:

~~~text
score = 0
HighUtilization contributes +25
LatePayment contributes +40
TrustedHistory contributes -15
final score = 50
~~~

Explanation nên ghi từng contribution, nguồn và tổng sau mỗi bước. Nếu score có cap, floor hoặc normalization, các phép biến đổi đó cũng cần được thể hiện.

### Override

Một rule có thể override kết quả trước đó. Explanation cần nêu giá trị trước, giá trị sau, rule thực hiện override và policy cho phép hành động đó.

### Default decision

Nếu không có rule nào match, engine có thể dùng default outcome. Cần hiển thị `DEFAULT_APPLIED` và cấu hình default, không nên tạo một lý do giả như một rule đã match.

### Manual review

Một decision có thể chuyển sang manual review khi dữ liệu thiếu, rule xung đột hoặc confidence thấp. Explanation nên nói rõ điều kiện chuyển review và thông tin người xử lý cần xem.

## 12. Reason code và reason hierarchy

Reason code là mã ổn định đại diện cho một lý do nghiệp vụ. Nó giúp API, report, UI và hệ thống downstream dùng cùng một taxonomy.

Ví dụ:

~~~text
HIGH_VALUE_ORDER
CUSTOMER_NOT_VERIFIED
RISK_THRESHOLD_EXCEEDED
MISSING_REQUIRED_DOCUMENT
MANUAL_REVIEW_REQUIRED
~~~

### Vì sao cần reason code?

Không nên dùng nguyên văn câu giải thích làm machine-readable contract vì wording có thể thay đổi, cần dịch hoặc điều chỉnh theo người dùng. Reason code ổn định giúp thống kê và tích hợp.

### Reason hierarchy

Reason có thể được tổ chức thành nhóm:

~~~text
ELIGIBILITY
  INELIGIBLE_CUSTOMER
  MISSING_DOCUMENT

RISK
  RISK_THRESHOLD_EXCEEDED
  SUSPICIOUS_ACTIVITY

POLICY
  HIGH_VALUE_ORDER
  REQUIRES_MANAGER_APPROVAL
~~~

Hierarchy giúp UI nhóm lý do và hỗ trợ báo cáo. Cần tránh thay đổi code hoặc meaning mà không version hóa contract.

### Primary và contributing reasons

Một kết quả có thể có một lý do chính và nhiều lý do đóng góp. Ví dụ quyết định `REJECTED` có primary reason là `RISK_THRESHOLD_EXCEEDED`, trong khi các reason khác chỉ cung cấp ngữ cảnh.

### Reason không phải rule ID

Rule ID định danh implementation/policy element; reason code mô tả lý do nghiệp vụ. Một reason có thể được tạo bởi nhiều rule khác nhau qua các version. Giữ hai identity riêng giúp thay đổi implementation mà không phá contract hiển thị.

## 13. Tạo explanation trong DSL

DSL có thể cho phép tác giả rule khai báo reason code và message template cùng với rule.

Ví dụ:

~~~text
rule HighValueOrder {
    when order.total >= 1000;
    then requireManagerApproval;

    explain {
        code = "HIGH_VALUE_ORDER";
        message = "Order total exceeds the automatic approval limit.";
        parameters = [order.total, 1000];
        category = "ELIGIBILITY";
    }
}
~~~

Đây là cú pháp minh họa. Một implementation cần xác định message template, parameter binding, localization và cách xử lý khi expression chứa dữ liệu nhạy cảm.

### Explanation metadata trong rule

Một rule có thể khai báo:

- Reason code.
- Nhóm lý do.
- Message template hoặc message key.
- Parameters được phép đưa vào message.
- Mức độ hiển thị.
- Audience được phép xem.
- Liên kết tới policy documentation.
- Version của explanation contract.

### Không nên hard-code mọi câu chữ vào engine

Engine nên tạo structured reason và parameter. UI hoặc presentation layer có thể dịch, định dạng số và tạo câu chữ theo audience. Điều này tránh trộn logic nghiệp vụ với ngôn ngữ hiển thị.

### Reason có thể phát sinh từ tổ hợp nhiều rule

Một lý do tổng hợp có thể phụ thuộc nhiều rule. Ví dụ `MANUAL_REVIEW_REQUIRED` có thể được tạo khi một rule yêu cầu review hoặc khi hai rule tạo kết quả xung đột. Explanation cần lưu contribution source để người đọc truy ngược được.

## 14. Thiết kế message và ngôn ngữ giải thích

Một explanation thân thiện cần nói rõ sự kiện và ý nghĩa, tránh thuật ngữ nội bộ không cần thiết.

So sánh:

| Cách diễn đạt | Vấn đề hoặc ưu điểm |
|---|---|
| `Rule HVO_01 fired.` | Hữu ích cho developer nhưng không nói lý do nghiệp vụ. |
| `Tổng đơn hàng là 1.500, vượt ngưỡng tự động phê duyệt 1.000.` | Nêu dữ liệu và ngưỡng có ý nghĩa. |
| `Decision node 0x8A3 returned false.` | Chi tiết nội bộ, khó hiểu với người dùng. |
| `Hồ sơ chưa đủ thông tin xác minh nên cần bổ sung tài liệu.` | Nêu trạng thái và bước tiếp theo. |

### Message template

Một message template có thể dùng key và parameter:

~~~text
messageKey: decision.high_value_order
parameters:
  amount: 1500
  threshold: 1000
~~~

Presentation layer có thể tạo câu phù hợp với locale. Không nên lưu một câu tiếng Việt duy nhất nếu hệ thống cần hỗ trợ nhiều ngôn ngữ.

### Hiển thị giá trị

Giá trị số cần format theo locale, currency và precision. `1500.00 USD` có thể được hiển thị khác nhau tùy locale. Tuy nhiên, structured record vẫn cần giữ giá trị typed để không mất độ chính xác.

### Tránh câu chữ kết luận quá mức

Nếu engine chỉ phát hiện tín hiệu rủi ro, explanation nên nói “có dấu hiệu cần xem xét” thay vì khẳng định hành vi gian lận. Explanation phải phản ánh đúng mức độ bằng chứng mà rule cung cấp.

### Nêu bước tiếp theo

Khi kết quả cần hành động, có thể nêu rõ tài liệu cần bổ sung, nhóm cần phê duyệt hoặc bước kiểm tra tiếp theo. Hành động đề xuất phải đến từ policy đã định nghĩa, không được tự suy diễn ngoài kết quả engine.

## 15. Giải thích rule không match

Việc giải thích vì sao rule không match thường khó hơn giải thích vì sao rule match, nhất là khi có nhiều điều kiện.

Ví dụ:

~~~text
rule TrustedCustomerDiscount {
    when customer.status == TRUSTED
      and customer.ageInMonths >= 12
      and order.total >= 500;
    then applyDiscount(10);
}
~~~

Input:

~~~text
status = TRUSTED
ageInMonths = 8
order.total = 900
~~~

Explanation:

~~~text
Rule: TrustedCustomerDiscount
Status: NOT_MATCHED

Condition 1: TRUSTED == TRUSTED -> true
Condition 2: 8 >= 12 -> false
Condition 3: 900 >= 500 -> true

Overall: false
Primary failed condition: customer.ageInMonths >= 12
~~~

### Tất cả điều kiện hay chỉ điều kiện đầu tiên?

Nếu DSL dùng short-circuit, engine có thể chỉ đánh giá đến điều kiện đủ để xác định kết quả. Muốn hiển thị mọi điều kiện, không nên tự chạy lại các expression nếu chúng có side effect hoặc đọc dữ liệu thay đổi. Có thể thiết kế một chế độ explain evaluation riêng chỉ cho expression thuần, hoặc ghi trace đầy đủ trong lần chạy gốc.

### Missing data

Nếu `customer.ageInMonths` không có, explanation cần thể hiện `UNKNOWN` hoặc `MISSING_INPUT` theo semantics. Không nên trình bày như thể giá trị là 0.

### Scope và disabled rule

Rule có thể không được đánh giá do scope, date window, tenant, feature flag hoặc trạng thái disabled. Đây là skip reason, không phải failed condition.

## 16. Giải thích rule đã match nhưng không tạo kết quả cuối

Một rule có thể match nhưng không đóng góp vào outcome cuối cùng.

Các trường hợp thường gặp:

- Activation bị rule priority cao hơn vượt qua.
- Decision dùng first-hit policy và đã dừng trước đó.
- Rule thuộc nhóm mutual exclusion và bị loại.
- Action bị cancel do execution kết thúc.
- Kết quả được aggregate nhưng contribution bằng 0 hoặc bị giới hạn.
- Một rule khác override output.
- Rule match trong nhánh không được chọn.

Explanation nên tách các trạng thái:

~~~text
conditionStatus = MATCHED
activationStatus = CREATED
executionStatus = SUPPRESSED
contributionStatus = NOT_INCLUDED
~~~

Nếu chỉ hiển thị `MATCHED`, người dùng có thể hiểu nhầm rằng rule đó đã quyết định kết quả. Nếu chỉ hiển thị `NOT_MATCHED`, trace sẽ sai sự thật.

## 17. Giải thích kết quả trong forward chaining

Forward chaining bắt đầu từ facts đã biết rồi áp dụng rule để suy ra facts hoặc hành động mới. Fact mới có thể kích hoạt rule tiếp theo.

Ví dụ:

~~~text
rule VerifyCustomer {
    when customer.documentsVerified == true;
    then assert customer.verified = true;
}

rule EligibleForCredit {
    when customer.verified == true
      and customer.income >= 2000;
    then assert customer.creditEligible = true;
}

rule ApproveCredit {
    when customer.creditEligible == true;
    then approveCredit;
}
~~~

Một trace có thể là:

1. Fact `documentsVerified = true` tồn tại.
2. `VerifyCustomer` match và tạo fact `verified = true`.
3. Fact mới kích hoạt `EligibleForCredit`.
4. Rule match vì income là 2.500.
5. Fact `creditEligible = true` được tạo.
6. `ApproveCredit` match và action được thực thi.

### Fact provenance

Mỗi derived fact nên lưu nguồn tạo: rule ID, execution ID, input facts và action. Nếu một fact được nhiều rule hỗ trợ, có thể lưu nhiều provenance path.

### Truth maintenance

Nếu fact nguồn bị rút lại hoặc thay đổi, engine có thể cần rút các fact dẫn xuất phụ thuộc. Explanation cần thể hiện fact nào bị invalidated và rule nào không còn được hỗ trợ.

## 18. Giải thích kết quả trong backward chaining

Backward chaining bắt đầu từ goal hoặc query rồi tìm các rule có thể chứng minh goal đó.

Ví dụ goal `customerEligible` có thể được chứng minh bởi:

~~~text
customerEligible if
    customerVerified
    and incomeAboveThreshold;

customerVerified if
    documentsVerified
    and identityMatched;
~~~

Explanation có thể trình bày cây chứng minh:

~~~text
Goal: customerEligible -> PROVED
├── customerVerified -> PROVED
│   ├── documentsVerified -> PROVED
│   └── identityMatched -> PROVED
└── incomeAboveThreshold -> PROVED
~~~

Nếu goal không được chứng minh, cần phân biệt:

- Có bằng chứng phủ định.
- Không có đủ dữ liệu.
- Không có rule nào hỗ trợ goal.
- Có chu kỳ suy luận chưa được giải quyết.
- Search bị dừng do giới hạn tài nguyên.

“Không chứng minh được” không luôn đồng nghĩa “đã chứng minh là sai”. Explanation phải theo logic của engine, đặc biệt nếu DSL dùng non-monotonic reasoning hoặc negation-as-failure.

## 19. Giải thích kết quả trong decision table và DMN-style decision

Decision model thường tách input data, decision node, decision table và output. Explanation nên liên kết kết quả node với các input node và rule row đã sử dụng.

Một decision graph có thể là:

~~~text
Application
  |
  v
ApplicantRisk -----> Eligibility
  |                     |
  v                     v
CreditLimit <-------- Decision
~~~

### Decision dependency

Nếu `CreditLimit` phụ thuộc `ApplicantRisk` và `Eligibility`, explanation cần cho biết output nào được tính trước, giá trị nào được truyền vào và dependency nào làm kết quả thay đổi.

### Hit policy explanation

Với decision table, cần lưu hit policy, các row match, output từng row và cách aggregation/selection.

### Decision requirement graph

Một decision có thể phụ thuộc nhiều input và decision khác. Trace graph giúp người đọc đi từ kết quả cuối ngược về các nguồn dữ liệu và rule row.

### Reuse decision result

Nếu một decision node được dùng bởi nhiều node khác, cần định danh execution/call context để giải thích kết quả trong đúng đường đi, tránh ghép nhầm output của hai lần đánh giá.

## 20. Giải thích kết quả có dữ liệu thiếu hoặc không chắc chắn

Một quyết định có thể không đủ thông tin để kết luận.

Các trạng thái dữ liệu có thể gồm:

- `PRESENT`: có giá trị hợp lệ.
- `MISSING`: không có dữ liệu.
- `NULL`: dữ liệu hiện diện nhưng giá trị null.
- `INVALID`: dữ liệu không đúng schema/kiểu.
- `STALE`: dữ liệu quá cũ theo freshness policy.
- `UNKNOWN`: chưa thể xác định.
- `REDACTED`: giá trị bị ẩn theo quyền truy cập.

### Three-valued logic

Nếu DSL hỗ trợ `TRUE`, `FALSE` và `UNKNOWN`, truth table của `and`, `or`, `not` cần được định nghĩa. Explanation cần ghi kết quả từng operand để người đọc hiểu vì sao tổng thể là unknown.

Ví dụ:

~~~text
customer.isVerified == true   -> UNKNOWN (missing data)
order.total >= 1000           -> TRUE
UNKNOWN and TRUE              -> UNKNOWN
decision                      -> MANUAL_REVIEW
~~~

### Confidence

Một số engine dùng confidence hoặc probability. Explanation cần phân biệt confidence của nguồn dữ liệu, score do rule tính và xác suất đã được hiệu chuẩn. Không nên trình bày một score như xác suất nếu mô hình không định nghĩa như vậy.

### Data freshness

Nếu dữ liệu được lấy từ nguồn cập nhật chậm, explanation có thể ghi timestamp và freshness status. Một quyết định dựa trên dữ liệu cũ có thể cần cảnh báo hoặc yêu cầu đánh giá lại.

## 21. Giải thích action và side effect

Rule có thể thực hiện action như gửi thông báo, cập nhật trạng thái, tạo task hoặc gọi service. Explanation cần cho biết action đã được yêu cầu, bắt đầu, thành công, thất bại hay bị hủy.

Một action record có thể gồm:

~~~text
ActionExecution
  actionId
  ruleId
  status
  startedAt
  completedAt
  inputSummary
  outputSummary
  errorCode
  retryCount
~~~

### Match không đảm bảo action thành công

Rule có thể match nhưng service call thất bại. Outcome nghiệp vụ có thể vẫn là `PENDING` hoặc chuyển sang `ERROR`. Explanation cần phân biệt lý do rule được kích hoạt với kết quả thực thi action.

### Retry

Nếu action retry, trace nên ghi từng attempt hoặc ít nhất số lần thử, lỗi transient và kết quả cuối. Không nên hiển thị một action thành công ngay từ lần đầu nếu thực tế phải retry ba lần.

### Idempotency

Nếu action có side effect và được retry, cần ghi idempotency key hoặc operation identity theo policy. Explanation không cần lộ secret key nhưng nên thể hiện operation được deduplicate nếu điều đó ảnh hưởng kết quả.

### Compensation

Trong workflow hoặc rule process, action sau có thể thất bại và hệ thống chạy compensation. Explanation nên liên kết compensation với action gốc và ghi kết quả hoàn tác, thay vì xóa action ban đầu khỏi trace.

## 22. Explanation trace và event model

Một cách xây dựng explanation đáng tin cậy là ghi execution event có cấu trúc trong lúc engine chạy.

Ví dụ event:

~~~text
DecisionStarted
RuleEvaluated
ConditionEvaluated
RuleMatched
ActivationCreated
ConflictResolved
ActionStarted
ActionCompleted
DecisionCompleted
~~~

Mỗi event có thể chứa:

- Event ID và execution ID.
- Parent/cause event ID.
- Decision và rule identity/version.
- Timestamp hoặc logical sequence number.
- Source location.
- Status và reason code.
- Input/output summary.
- Data provenance reference.

### Event sequence

Sequence number giúp xác định thứ tự trong một execution. Timestamp đơn thuần có thể không đủ khi nhiều event xảy ra gần nhau hoặc đồng hồ giữa process không đồng bộ.

### Causality

Cause/parent link cho biết event nào kích hoạt event tiếp theo. Trong forward chaining, một `FactAsserted` có thể là nguyên nhân tạo `RuleActivated`. Trong distributed decision, trace context có thể liên kết service call và callback.

### Event sourcing và explanation

Nếu engine lưu event đầy đủ, explanation có thể được tổng hợp từ event stream. Tuy nhiên, event sourcing không tự động bảo đảm explanation dễ hiểu; cần một projection layer tổng hợp event kỹ thuật thành reason và narrative.

### Trace granularity

Ghi mọi phép toán có thể tạo lượng dữ liệu rất lớn. Có thể cung cấp nhiều trace level: summary, rule-level, condition-level và full execution. Mức ghi cần được chọn theo nhu cầu và policy dữ liệu.

## 23. Thiết kế API trả explanation

API nên tách outcome ổn định khỏi presentation text và trace chi tiết.

Ví dụ response:

~~~json
{
  "executionId": "exec-2026-00125",
  "decision": "OrderApproval",
  "decisionVersion": "12",
  "outcome": {
    "code": "REQUIRES_REVIEW",
    "label": "Cần quản lý phê duyệt"
  },
  "reasons": [
    {
      "code": "HIGH_VALUE_ORDER",
      "category": "ELIGIBILITY",
      "parameters": {
        "amount": 1500,
        "threshold": 1000
      },
      "contribution": "PRIMARY"
    }
  ],
  "trace": {
    "reference": "trace-00125",
    "detailLevel": "RULE"
  }
}
~~~

Đây là ví dụ hợp đồng API minh họa. Schema thực tế cần định nghĩa rõ field bắt buộc, kiểu, version và cách phân trang trace.

### Outcome code

Outcome code nên ổn định và machine-readable. Label có thể được dịch hoặc thay đổi cách diễn đạt.

### Reason code và parameters

Reason code là identity của lý do; parameters chứa dữ liệu có kiểu để presentation layer tạo message. Cần xác định parameter nào được phép trả ra ngoài.

### Trace reference

Trace chi tiết có thể được truy xuất qua endpoint riêng để response chính không quá lớn. Trace reference cần có authorization và retention policy.

### Detail level

Caller có thể yêu cầu mức summary hoặc detailed nếu được cấp quyền. Không nên cho client tùy ý yêu cầu mọi dữ liệu nội bộ nếu điều đó có thể làm lộ policy hoặc thông tin nhạy cảm.

### API versioning

Thay đổi taxonomy reason, cấu trúc trace hoặc semantics outcome cần có versioning. Client không nên phải parse câu chữ để xác định logic.

## 24. Trình bày explanation cho nhiều đối tượng

Một execution có thể cần nhiều dạng explanation khác nhau.

### Người dùng cuối

Ưu tiên kết quả, lý do chính, thông tin cần bổ sung và bước tiếp theo. Không hiển thị rule ID, internal variable hoặc chi tiết triển khai không cần thiết.

Ví dụ:

~~~text
Đơn hàng cần quản lý phê duyệt vì tổng giá trị 1.500 vượt ngưỡng tự động 1.000.
Bạn có thể gửi yêu cầu phê duyệt để tiếp tục xử lý.
~~~

### Chuyên gia nghiệp vụ

Hiển thị rule match, failed conditions, priority, policy version và dữ liệu liên quan để kiểm tra tính đúng đắn của quy tắc.

### Developer

Hiển thị source location, rule/node ID, condition tree, fact binding, execution order, activation và lỗi runtime.

### Auditor/compliance reviewer

Hiển thị principal, execution time, decision version, input provenance, policy version, reason codes, approval và evidence integrity.

### Operator/support

Hiển thị action status, service dependency, retry, timeout và correlation ID cần cho điều tra vận hành.

### Một trace, nhiều projection

Có thể lưu một structured trace chuẩn rồi tạo các projection theo audience. Cách này tránh duy trì nhiều nguồn explanation không đồng bộ.

## 25. Bảo mật và quyền truy cập explanation

Explanation có thể tiết lộ dữ liệu cá nhân, điều kiện chống gian lận, ngưỡng nội bộ hoặc logic chính sách. Không phải mọi người được xem cùng một mức chi tiết.

### Data minimization

Chỉ thu thập và hiển thị dữ liệu cần thiết để giải thích. Nếu chỉ cần biết `incomeBelowThreshold`, không nhất thiết phải hiển thị toàn bộ hồ sơ thu nhập.

### Redaction

Giá trị nhạy cảm có thể được che hoặc thay bằng category. Structured trace vẫn có thể giữ reference đến evidence được bảo vệ riêng.

### Role-based access

Người dùng cuối có thể xem reason code và message; chuyên gia policy xem điều kiện; developer xem trace kỹ thuật; auditor xem provenance theo quyền. Authorization phải được kiểm tra ở server, không chỉ ẩn field trong UI.

### Policy confidentiality

Trong một số hệ thống, hiển thị toàn bộ rule hoặc threshold có thể giúp người dùng thao túng kết quả. Có thể cung cấp lý do ở mức đủ minh bạch mà không tiết lộ chi tiết chống gian lận. Quyết định mức công bố cần dựa trên policy và yêu cầu pháp lý, không được tùy tiện làm explanation sai lệch.

### Tenant isolation

Execution, trace và evidence của tenant này không được truy cập từ tenant khác. Trace ID khó đoán không thay thế authorization.

### Retention và deletion

Explanation có thể chứa dữ liệu cá nhân hoặc thông tin nghiệp vụ. Cần retention, deletion và legal hold phù hợp. Có thể lưu reason code lâu hơn raw input nếu chính sách cho phép.

### Integrity

Với quyết định quan trọng, có thể ký hoặc hash execution evidence để phát hiện chỉnh sửa. Integrity metadata cần gắn với version và phạm vi dữ liệu được bảo vệ.

## 26. Tính tái lập và replay quyết định

Một explanation có giá trị khi có thể xác định quyết định được tạo từ dữ liệu và policy nào.

### Pin decision version

Mỗi execution cần ghi decision/rule version, language version và engine version. Nếu rule được sửa sau đó, explanation lịch sử vẫn phải chỉ đến version đã thực thi.

### Pin input snapshot

Ghi nhận input đã chuẩn hóa hoặc reference đến snapshot có thể truy xuất. Không nên chỉ lưu request ID nếu dữ liệu nguồn có thể thay đổi hoặc bị xóa.

### External data

Nếu rule đọc dữ liệu từ service ngoài, cần ghi value/version/time hoặc evidence reference phù hợp. Replay gọi lại service hiện tại có thể cho kết quả khác.

### Clock và randomness

Rule có thể phụ thuộc thời gian, random value hoặc sequence. Nếu cần tái lập, ghi clock instant, timezone, random seed hoặc giá trị đã sinh. Không nên giả định replay dùng đồng hồ hiện tại sẽ tái tạo kết quả lịch sử.

### Engine semantics

Engine version có thể thay đổi thứ tự rule, type coercion hoặc behavior. Replay cần đúng semantics version hoặc một compatibility layer có chủ đích.

### Replay không phải lúc nào cũng an toàn

Nếu rule action gửi email, thu tiền hoặc cập nhật hệ thống, chạy lại execution có thể tạo side effect lặp. Có thể cung cấp dry-run/replay mode chỉ đánh giá và không thực thi action, hoặc dùng sandbox cùng idempotency controls.

## 27. So sánh explanation giữa hai phiên bản decision

Khi policy thay đổi, tổ chức có thể muốn biết cùng một input sẽ cho kết quả khác ra sao.

Quy trình:

1. Giữ nguyên input snapshot.
2. Chạy decision version cũ ở chế độ replay/dry-run.
3. Chạy version mới với cùng semantics đầu vào.
4. So sánh outcome, matched rules, reason codes và contribution.
5. Xác định rule hoặc threshold tạo khác biệt.

Ví dụ:

| Thành phần | Version 11 | Version 12 |
|---|---|---|
| HighValueOrder threshold | 1.500 | 1.000 |
| Rule matched | Không | Có |
| Outcome | APPROVED | REQUIRES_REVIEW |
| Primary reason | AUTO_APPROVAL | HIGH_VALUE_ORDER |

### Counterfactual explanation

Counterfactual giải thích thay đổi tối thiểu nào có thể làm kết quả khác. Ví dụ: “Nếu tổng đơn hàng thấp hơn 1.000, rule yêu cầu quản lý sẽ không match.”

Counterfactual cần được tính dựa trên semantics và constraint thực tế. Không nên đề xuất thay đổi dữ liệu giả tạo hoặc không thể kiểm soát như thể đó là hướng dẫn chắc chắn để đạt kết quả mong muốn.

### What-if analysis

What-if cho phép thay đổi input giả định và chạy lại decision trong môi trường an toàn. Kết quả cần được đánh dấu simulation, không nhầm với quyết định chính thức.

## 28. Giải thích score và mô hình quyết định kết hợp

Một DSL có thể kết hợp rule-based logic với score hoặc mô hình dự đoán.

Ví dụ:

~~~text
score RiskScore(application) {
    base = 20;
    if latePayments > 2 then base += 30;
    if verifiedIncome then base -= 10;
    if suspiciousDevice then base += 40;
}

decision RiskOutcome(application) {
    when RiskScore(application) >= 80 then REJECT;
    when RiskScore(application) >= 50 then REVIEW;
    otherwise APPROVE;
}
~~~

Explanation cần tách:

- Score đầu vào hoặc baseline.
- Contribution của từng rule/feature.
- Các phép biến đổi, clamp hoặc normalization.
- Ngưỡng quyết định.
- Rule quyết định outcome cuối.

### Contribution không đồng nghĩa causation

Một feature có contribution trong score không tự động chứng minh nó là nguyên nhân duy nhất của kết quả. Explanation nên nói “đóng góp vào score” hoặc “được sử dụng bởi rule” thay vì tuyên bố quan hệ nhân quả nếu hệ thống không chứng minh được.

### Score calibration

Nếu score được trình bày như probability, cần có calibration phù hợp. Nếu chỉ là điểm heuristic, UI phải gọi là score và giải thích thang đo.

### Feature attribution

Nếu có mô hình bên ngoài, explanation có thể lấy attribution từ model service. Cần ghi model version và phương pháp attribution; không tự suy ra feature importance từ output cuối.

## 29. Explainability cho quyết định bất lợi và khiếu nại

Khi outcome gây bất lợi, explanation cần đủ cụ thể để người nhận hiểu vấn đề và biết cách yêu cầu xem xét.

Một explanation hữu ích nên:

- Nêu outcome bằng ngôn ngữ rõ ràng.
- Đưa ra reason code ổn định.
- Mô tả yếu tố hoặc điều kiện chính đã ảnh hưởng.
- Phân biệt dữ liệu thiếu với dữ liệu không đạt điều kiện.
- Chỉ ra thông tin có thể cập nhật hoặc quy trình xem xét lại nếu có.
- Ghi nhận version và thời điểm quyết định.
- Cho phép người có thẩm quyền xem trace chi tiết.

### Không đưa ra lý do giả

Nếu decision engine từ chối vì một rule kỹ thuật bị cấu hình sai, không nên trình bày như thể khách hàng vi phạm một tiêu chí nghiệp vụ. Cần tách business rejection khỏi execution failure và chuyển lỗi kỹ thuật đến quy trình phù hợp.

### Human review

Một người có thẩm quyền có thể xem lại dữ liệu và policy. Explanation nên cung cấp evidence, không áp đặt rằng kết quả tự động là không thể thay đổi.

### Correction và appeal

Nếu người dùng có thể sửa dữ liệu hoặc khiếu nại, explanation nên chỉ ra kênh và loại thông tin cần cung cấp. Không tiết lộ chi tiết có thể làm lộ cơ chế chống gian lận vượt quá policy cho phép.

## 30. Thiết kế explanation DSL có version

Reason code và message contract cần được quản lý như một phần public interface của decision DSL.

Một cấu trúc khái niệm:

~~~text
explanationDefinition HighValueOrderReason {
    code = "HIGH_VALUE_ORDER";
    category = "ELIGIBILITY";
    severity = "INFO";
    messageKey = "decision.high_value_order";
    parameters {
        amount: Money;
        threshold: Money;
    }
    audience = [CUSTOMER, OPERATOR, AUDITOR];
}
~~~

### Reason schema

Mỗi reason cần định nghĩa code, category, parameter types, audience, localization key và semantics. Thay đổi parameter bắt buộc có thể là breaking change với client.

### Message catalog

Message text có thể được quản lý trong resource bundle riêng. Reason code liên kết với message key; locale resolver chọn bản dịch phù hợp.

### Backward compatibility

Nếu đổi message wording nhưng giữ code và parameters, API client có thể tiếp tục hoạt động. Nếu thay đổi ý nghĩa reason code, nên tạo code mới hoặc version contract.

### Deprecated reasons

Reason cũ có thể được đánh dấu deprecated nhưng vẫn cần đọc được trong historical record. Không tái sử dụng code cũ cho ý nghĩa mới.

### Unknown reason code

Consumer cũ có thể nhận code mới. Cần fallback hiển thị an toàn như label chung hoặc message key, đồng thời giữ raw code để telemetry và support.

## 31. Hiệu năng và chi phí thu thập explanation

Ghi explanation chi tiết có thể tốn CPU, memory và storage, đặc biệt khi decision đánh giá hàng nghìn rule.

### Trace level

Có thể cung cấp:

- Summary: outcome và primary reasons.
- Rule: trạng thái từng rule.
- Condition: từng predicate và operand result.
- Full: mọi event, fact lineage, activation và action.

### Lazy detail

Engine có thể lưu trace compact hoặc reference đến event store, chỉ tải condition detail khi người có quyền yêu cầu. Tuy nhiên, nếu không ghi dữ liệu lúc execution, không thể luôn tái tạo chính xác sau này.

### Sampling

Sampling có thể dùng cho telemetry hiệu năng, nhưng không phù hợp nếu mọi quyết định cần explanation hoặc audit. Cần phân biệt sampling observability với lưu explanation bắt buộc.

### Aggregation

Với rule chạy lặp trên nhiều record, có thể tổng hợp số lần match và reason counts thay vì lưu toàn bộ payload. Với từng quyết định cá nhân, cần giữ identity và evidence theo yêu cầu nghiệp vụ.

### Storage tiers

Summary có thể lưu lâu hơn full trace; raw input có thể có retention ngắn hơn; audit metadata có thể được giữ theo policy. Cần bảo đảm trace reference không trỏ đến dữ liệu đã bị xóa mà API vẫn hứa có thể truy cập.

## 32. Observability và correlation

Explanation thường liên quan đến nhiều service hoặc execution bất đồng bộ. Cần ID để nối các sự kiện.

Các identity hữu ích:

- `executionId`: một lần chạy decision.
- `decisionId` và `decisionVersion`: định danh chương trình.
- `ruleId` và `ruleVersion`: định danh rule.
- `traceId`: liên kết distributed trace.
- `correlationId`: liên kết các hoạt động cùng nghiệp vụ.
- `causationId`: xác định event/action gây ra bước hiện tại.
- `factId`: định danh fact hoặc snapshot data.
- `actionExecutionId`: định danh một lần thực thi action.

### Structured logging

Log nên chứa identity và event code, không chỉ message tự do. Điều này giúp truy vấn execution, tổng hợp lỗi và liên kết với explanation record.

### Metrics

Các metrics có thể gồm:

- Số execution theo outcome/reason.
- Tỷ lệ rule match và không match.
- Tần suất evaluation error.
- Thời gian đánh giá theo decision/rule.
- Số activation bị suppress.
- Kích thước trace và storage cost.
- Tỷ lệ execution có explanation đầy đủ.
- Số request bị từ chối do authorization.

### Không dùng metric label có cardinality vô hạn

Execution ID hoặc user ID không nên trở thành metric label nếu tạo cardinality rất lớn. Dùng trace/log cho identity chi tiết và metric label cho dimension có giới hạn.

## 33. Kiểm thử explanation

Một decision đúng nhưng explanation sai vẫn có thể làm người dùng hiểu sai. Vì vậy, explanation cần được kiểm thử như một output có contract.

### Rule trace test

Với input cố định, xác nhận rule nào được đánh giá, match, fire, skip hoặc error.

### Condition trace test

Kiểm tra operand values, short-circuit, null/unknown và overall result.

### Conflict resolution test

Tạo nhiều rule cùng match và xác nhận priority, hit policy, agenda order hoặc mutual exclusion được giải thích chính xác.

### Reason code test

Xác nhận outcome gắn đúng primary/contributing reasons, parameters đủ kiểu và code ổn định.

### Negative explanation test

Kiểm tra rule không match, rule bị skip, action bị cancel và rule match nhưng không đóng góp cuối cùng.

### Data lineage test

Xác nhận fact derived có nguồn và phép biến đổi đúng, external data có timestamp/version.

### Security test

Xác nhận role khác nhau nhận detail khác nhau, secret được redacted và tenant isolation được giữ.

### Replay test

Chạy lại với cùng version/input snapshot và xác nhận outcome cùng explanation semantics, kể cả khi clock hoặc external dependency được mô phỏng.

### Contract test

Kiểm tra JSON schema, reason code catalog, localization fallback và client xử lý unknown reason.

### Snapshot/golden test

Lưu explanation mẫu để phát hiện thay đổi ngoài ý muốn. Không nên so sánh câu chữ duy nhất nếu localization hoặc wording được phép thay đổi; cần so sánh structured reason và trace semantics.

## 34. Ví dụ Java: biểu diễn explanation có cấu trúc

Một implementation có thể dùng kiểu dữ liệu riêng cho outcome, reason và rule evaluation.

~~~java
enum EvaluationStatus {
    NOT_EVALUATED,
    SKIPPED,
    MATCHED,
    NOT_MATCHED,
    UNKNOWN,
    EVALUATION_ERROR,
    FIRED,
    SUPPRESSED
}

record Reason(
    String code,
    String category,
    Map<String, Object> parameters,
    boolean primary
) {}

record RuleEvaluation(
    String ruleId,
    String ruleVersion,
    EvaluationStatus status,
    String skipReason,
    String sourceLocation
) {}

record DecisionExplanation(
    String executionId,
    String decisionId,
    String decisionVersion,
    String outcomeCode,
    List<Reason> reasons,
    List<RuleEvaluation> ruleEvaluations
) {}
~~~

Đây là mô hình minh họa. Trong hệ thống thực tế, `Map<String, Object>` có thể được thay bằng typed value model hoặc JSON value schema để tránh mất kiểu và kiểm soát serialization tốt hơn.

### Ghi evaluation trong lúc chạy

~~~java
final class ExplanationCollector {
    private final List<RuleEvaluation> evaluations = new ArrayList<>();
    private final List<Reason> reasons = new ArrayList<>();

    void record(RuleEvaluation evaluation) {
        evaluations.add(evaluation);
    }

    void addReason(Reason reason) {
        reasons.add(reason);
    }

    List<RuleEvaluation> evaluations() {
        return List.copyOf(evaluations);
    }

    List<Reason> reasons() {
        return List.copyOf(reasons);
    }
}
~~~

Collector nên thuộc execution context hoặc được truyền rõ ràng, tránh static mutable state dùng chung giữa nhiều decision execution. Với engine concurrent, mỗi execution cần collector hoặc event stream độc lập.

### Tách execution khỏi presentation

Engine ghi `HIGH_VALUE_ORDER` cùng parameter typed. Presentation service chọn message tiếng Việt hoặc tiếng Anh, format tiền tệ và áp dụng quyền redaction. Cách này giúp logic quyết định không phụ thuộc giao diện hoặc locale.

## 35. Ví dụ explanation hoàn chỉnh

Input:

~~~json
{
  "orderId": "ORD-1042",
  "total": 1500,
  "currency": "USD",
  "customerStatus": "TRUSTED",
  "riskScore": 25
}
~~~

Decision DSL:

~~~text
decision OrderApproval(order) {
    rule FraudAlert priority 200 {
        when order.riskScore >= 90;
        then reject;
        explain code "RISK_THRESHOLD_EXCEEDED";
    }

    rule HighValueOrder priority 100 {
        when order.total >= 1000;
        then requireManagerApproval;
        explain code "HIGH_VALUE_ORDER";
    }

    rule TrustedCustomer priority 80 {
        when order.customerStatus == TRUSTED;
        then approve;
        explain code "TRUSTED_CUSTOMER";
    }
}
~~~

Một execution trace minh họa:

~~~text
Decision: OrderApproval@12
Execution: exec-1042

FraudAlert
  condition: 25 >= 90 -> false
  status: NOT_MATCHED

HighValueOrder
  condition: 1500 >= 1000 -> true
  status: MATCHED
  activation: CREATED

TrustedCustomer
  condition: TRUSTED == TRUSTED -> true
  status: MATCHED
  activation: CREATED

Conflict resolution
  strategy: PRIORITY
  selected: HighValueOrder (100)
  suppressed: TrustedCustomer (80)

Outcome: REQUIRES_REVIEW
Primary reason: HIGH_VALUE_ORDER
~~~

User-facing explanation:

~~~text
Đơn hàng ORD-1042 cần quản lý phê duyệt vì tổng giá trị 1.500 USD vượt ngưỡng tự động 1.000 USD.
Hồ sơ khách hàng thuộc nhóm tin cậy, nhưng theo chính sách hiện tại, rule xử lý đơn giá trị cao có mức ưu tiên cao hơn.
~~~

Ví dụ này minh họa vì sao explanation phải thể hiện cả rule match và conflict resolution. Nếu chỉ hiển thị “khách hàng tin cậy” hoặc “đơn hàng giá trị cao”, người đọc có thể không hiểu vì sao kết quả cuối là review thay vì approve.

## 36. Những lỗi thiết kế thường gặp

**Chỉ lưu outcome cuối.** Không thể biết rule nào hoặc dữ liệu nào dẫn đến kết quả; cần lưu structured reason và trace phù hợp.

**Coi mọi rule match là rule đã firing.** Match, activation, execute và contribute là các trạng thái khác nhau.

**Coi rule không match là rule chưa được đánh giá.** Short-circuit, scope, disabled và evaluation error cần trạng thái riêng.

**Chạy lại expression để tạo explanation.** Expression có thể phụ thuộc thời gian, random, external service hoặc side effect; explanation nên lấy từ execution gốc.

**Chỉ lưu câu chữ tự do.** Message khó thống kê, dịch và giữ tương thích; cần reason code cùng parameters có kiểu.

**Không ghi conflict resolution.** Khi nhiều rule cùng match, danh sách match không giải thích được vì sao một rule thắng.

**Biến missing data thành false.** Điều này làm sai semantics và có thể tạo quyết định bất lợi không có cơ sở.

**Không ghi version của decision.** Policy thay đổi khiến explanation lịch sử không thể tái lập hoặc xác minh.

**Đưa toàn bộ input vào explanation.** Có thể lộ dữ liệu nhạy cảm và làm người đọc khó tìm lý do thực sự.

**Tiết lộ quá nhiều policy detail.** Explanation cho người dùng cuối có thể vô tình lộ ngưỡng hoặc logic chống gian lận. Cần audience-based access.

**Dùng reason code làm rule ID.** Implementation thay đổi sẽ phá contract hiển thị và báo cáo.

**Không phân biệt action failure với decision outcome.** Rule có thể match nhưng action thất bại; không nên báo decision thành công.

**Không giữ provenance của derived fact.** Không thể truy ngược dữ liệu hoặc rule tạo ra fact được sử dụng.

**Không kiểm thử explanation.** Outcome có thể đúng nhưng message hoặc reason sai, gây hiểu lầm và rủi ro vận hành.

## 37. Quy trình thiết kế giải thích kết quả cho DSL luật và quyết định

Một quy trình thực tế có thể gồm:

1. **Xác định audience:** người dùng cuối, chuyên gia nghiệp vụ, developer, operator và auditor.
2. **Định nghĩa outcome contract:** outcome code, status và semantics của default/manual review/error.
3. **Mô hình hóa rule lifecycle:** evaluated, skipped, matched, activated, fired, suppressed và cancelled.
4. **Định nghĩa condition trace:** operand result, short-circuit, unknown/null và evaluation error.
5. **Theo dõi facts:** input, external data, derived facts, source, version và timestamp.
6. **Ghi conflict resolution:** priority, agenda, hit policy, group và aggregation.
7. **Thiết kế reason taxonomy:** primary/contributing reason, category, code và typed parameters.
8. **Tách message khỏi logic:** localization, formatting và audience projection.
9. **Thiết kế execution events:** sequence, parent/cause, trace ID và source location.
10. **Xác định API:** summary, detailed trace, pagination, versioning và authorization.
11. **Thiết kế security:** redaction, data minimization, policy confidentiality và retention.
12. **Bảo đảm replay:** pin decision/engine version, input snapshot, external data và clock.
13. **Kiểm thử:** positive/negative rules, conflict, missing data, reason contract, security và replay.
14. **Đo lường:** trace cost, explanation coverage, latency, storage và lỗi hiển thị.

## 38. Checklist cho một decision explanation

Trước khi phát hành explanation cho một quyết định, cần xác nhận:

- Outcome code và label có rõ ràng không?
- Decision/rule/engine version có được ghi lại không?
- Rule nào được đánh giá, match, skip hoặc lỗi?
- Có phân biệt match, activation, firing và contribution không?
- Condition trace có thể giải thích operand và short-circuit không?
- Missing, null và unknown có giữ đúng semantics không?
- Facts có source, timestamp và provenance cần thiết không?
- Conflict resolution và hit policy có được ghi lại không?
- Primary và contributing reasons có đúng không?
- Reason code có ổn định và parameters có kiểu không?
- Message có phù hợp audience và locale không?
- Action status có phân biệt success, failure, retry và cancellation không?
- Dữ liệu nhạy cảm đã được redacted theo quyền chưa?
- Trace có liên kết execution/correlation ID không?
- Có thể tái lập hoặc xác minh kết quả lịch sử không?
- Explanation có phân biệt business rejection với technical failure không?
- Có kiểm thử cho rule không match và rule bị suppress không?

## 39. Kết quả cần có sau khi thiết kế giải thích kết quả

Một cơ chế explanation hoàn chỉnh cho DSL luật và quyết định thường cung cấp:

- **Outcome contract:** kết quả machine-readable, status và semantics của decision.
- **Rule evaluation model:** trạng thái evaluated, skipped, matched, activated, fired, suppressed và error.
- **Condition trace:** cây biểu thức, operand values, short-circuit và unknown handling.
- **Fact provenance:** nguồn dữ liệu, derived fact, version, timestamp và freshness.
- **Conflict resolution record:** priority, agenda, hit policy, rule group và aggregation.
- **Reason taxonomy:** reason code, category, primary/contributing role và typed parameters.
- **Presentation layer:** message templates, localization, formatting và audience-specific projection.
- **Execution trace:** event sequence, causality, action status, source location và correlation.
- **API contract:** summary, detailed trace, versioning, pagination và authorization.
- **Security policy:** data minimization, redaction, policy confidentiality, tenant isolation và retention.
- **Replay evidence:** decision version, engine version, input snapshot, external data và clock context.
- **Test/observability strategy:** trace correctness, reason contract, privacy, replay, coverage, latency và storage cost.

Giải thích kết quả giúp biến output của rule engine thành một quyết định có thể hiểu, kiểm tra và truy vết. Để explanation đáng tin cậy, engine cần ghi nhận quá trình đánh giá ngay trong execution: dữ liệu được dùng, condition result, rule activation, conflict resolution, action status và reason code. Các trạng thái match, skip, fire và contribute phải được phân biệt; dữ liệu thiếu phải giữ đúng semantics; decision version và input provenance cần được pin để giải thích lịch sử. Presentation layer có thể tạo nhiều cách diễn đạt cho từng audience nhưng phải dựa trên cùng structured explanation. Khi kết hợp reason taxonomy ổn định, trace có quan hệ nhân quả, kiểm soát quyền truy cập và kiểm thử độc lập, DSL luật và quyết định có thể cung cấp kết quả minh bạch hơn mà vẫn bảo vệ dữ liệu và logic chính sách cần được giữ kín.
