# Tương thích ngữ nghĩa

Trong vòng đời của một DSL, grammar, type system, schema, runtime và các quy tắc nghiệp vụ đều có thể thay đổi. Một phiên bản mới có thể vẫn parse được source cũ, vẫn sinh ra artifact hợp lệ và vẫn giữ nguyên tên field, nhưng kết quả thực thi có thể khác. Ví dụ, phép chia số nguyên có thể đổi cách làm tròn, giá trị null có thể được xử lý khác, thứ tự áp dụng rule có thể thay đổi hoặc một default mới có thể làm request cũ tạo ra quyết định khác.

**Tương thích ngữ nghĩa (semantic compatibility)** là khả năng giữ nguyên ý nghĩa và hành vi mà consumer dựa vào khi các thành phần hoặc phiên bản thay đổi. Nó xem xét kết quả quan sát được của chương trình DSL, không chỉ cấu trúc cú pháp hoặc chữ ký API. Hai phiên bản có thể tương thích về syntax nhưng không tương thích về semantics; ngược lại, một số thay đổi cú pháp có thể được migration tự động mà vẫn giữ nguyên ý nghĩa.

Trong quản lý phiên bản và di trú, cần xác định hành vi nào là contract, thay đổi nào làm thay đổi ý nghĩa, consumer nào bị ảnh hưởng, cách phát hiện khác biệt và cách chuyển đổi an toàn. Điều này đặc biệt quan trọng khi DSL được dùng để sinh API, query, workflow, rule, schema, code hoặc quyết định nghiệp vụ cần tái hiện.

## 1. Tương thích ngữ nghĩa là gì?

Một thay đổi tương thích ngữ nghĩa khi mọi hành vi mà consumer được phép quan sát và dựa vào vẫn nằm trong contract đã cam kết, hoặc thay đổi được công bố rõ và không phá vỡ các consumer trong phạm vi hỗ trợ.

Ví dụ, một DSL định nghĩa:

~~~text
rule "discount" {
    when customer.isMember
    then discount = 0.10
}
~~~

Nếu phiên bản mới vẫn parse cùng source nhưng thay semantics của boolean null từ “không match” thành “match”, các quyết định có thể thay đổi. Syntax không đổi, nhưng semantics đã đổi.

Một ví dụ khác:

~~~text
price = 10 / 3
~~~

Nếu phiên bản cũ dùng integer division và trả 3, còn phiên bản mới tự động nâng sang decimal và trả 3.333..., chương trình vẫn hợp lệ nhưng kết quả thay đổi.

Tương thích ngữ nghĩa phải được đánh giá theo ngữ cảnh:
- DSL source author.
- API consumer.
- Runtime application.
- Plugin hoặc extension.
- Data/schema consumer.
- Build/generator pipeline.
- Người dùng cuối nhận kết quả nghiệp vụ.

Một thay đổi có thể tương thích với một nhóm nhưng không tương thích với nhóm khác. Vì vậy, cần xác định rõ consumer và contract trước khi phân loại thay đổi.

## 2. Phân biệt syntax, structure và semantics

Ba lớp tương thích thường bị nhầm lẫn:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Syntax compatibility | Source có parse được không? | Grammar mới còn nhận cú pháp cũ |
| Structural compatibility | Shape, type và interface có giữ không? | Field, method, schema vẫn tồn tại |
| Semantic compatibility | Hành vi và ý nghĩa có giữ không? | Kết quả, lỗi và side effect không đổi ngoài contract |

Ví dụ API vẫn có field amount: Decimal, nhưng phiên bản mới diễn giải amount là giá chưa thuế thay vì giá đã gồm thuế. Shape không đổi; semantics đã đổi.

Ví dụ schema vẫn giữ status: String, nhưng enum value PENDING giờ được hiểu là “đã gửi xử lý” thay vì “đang chờ người dùng xác nhận”. Structural compatibility không bảo đảm semantic compatibility.

Một đánh giá version đầy đủ cần xem cả ba lớp. Parser thành công chỉ chứng minh cú pháp được chấp nhận, không chứng minh kết quả giống trước.

## 3. Contract quan sát được

Không phải mọi chi tiết implementation đều là contract. Consumer thường quan sát:

- Giá trị trả về.
- Trạng thái hoặc quyết định.
- Thứ tự phần tử.
- Lỗi và error code.
- Side effect.
- Dữ liệu được lưu.
- Thời điểm hiệu lực.
- Độ chính xác số.
- Null/default behavior.
- Thời gian phản hồi trong giới hạn SLA.
- Tính xác định hoặc idempotency.
- Metadata và provenance được công bố.

Ví dụ, một API trả danh sách đơn hàng có thể không cam kết thứ tự nếu thiếu sort. Consumer không nên dựa vào thứ tự tình cờ. Nhưng nếu contract nói sắp xếp theo createdAt tăng dần, thay đổi sang giảm dần là breaking semantic change.

Cần ghi rõ điều gì được cam kết, điều gì là implementation detail và những behavior nào không được bảo đảm.

## 4. Behavioral contract của DSL

Một behavioral contract mô tả hành vi mà source hoặc consumer có thể dựa vào. Với DSL, contract có thể gồm:

- Operator semantics.
- Type conversion.
- Null propagation.
- Evaluation order.
- Scope và name resolution.
- Function behavior.
- Rule priority.
- Error handling.
- Transaction behavior.
- Time and timezone.
- Serialization.
- Query ordering.
- Default values.
- Side effect and retry behavior.

Ví dụ function contract:

~~~text
function normalizeEmail(value: String): String
    deterministic
    pure
    preservesLocalPartCase
    normalizesDomainCase
~~~

Nếu phiên bản mới bắt đầu lowercase toàn bộ email, hành vi đã thay đổi dù signature vẫn giống.

Một function contract tốt cần mô tả cả input domain, output, errors, side effects, determinism và compatibility expectations.

## 5. Phạm vi tương thích

Tương thích có thể được xét theo nhiều chiều:

- **Source compatibility:** source cũ vẫn được chấp nhận.
- **Binary compatibility:** artifact đã compile vẫn liên kết được với runtime mới.
- **Schema compatibility:** dữ liệu cũ và mới có thể được đọc/ghi theo contract.
- **API compatibility:** client cũ tiếp tục gọi được API.
- **Behavioral compatibility:** hành vi quan sát được không thay đổi ngoài contract.
- **Data compatibility:** dữ liệu lưu trước đó vẫn có thể được đọc và diễn giải đúng.
- **Operational compatibility:** deployment, build và runtime vẫn hoạt động với cấu hình được hỗ trợ.
- **Plugin compatibility:** extension cũ vẫn hoạt động với host API mới.

Một release có thể giữ source compatibility nhưng phá binary compatibility. Một schema có thể đọc được dữ liệu cũ nhưng diễn giải đơn vị khác. Cần nói rõ loại compatibility đang được cam kết.

## 6. Backward, forward và semantic compatibility

- **Backward compatibility:** phiên bản mới tiếp tục hỗ trợ artifact, source hoặc data được tạo bởi phiên bản cũ trong phạm vi công bố.
- **Forward compatibility:** consumer hoặc runtime cũ có thể xử lý một phần dữ liệu/extension từ phiên bản mới theo contract.
- **Semantic compatibility:** ý nghĩa và hành vi được consumer dựa vào vẫn được giữ hoặc thay đổi theo một migration có kiểm soát.

Ví dụ, server mới có thể chấp nhận request từ client cũ; đó là backward API compatibility. Client cũ có thể bỏ qua một field optional mới; đó là forward tolerance. Nhưng nếu default server thay đổi và request cũ không gửi field đó nhận kết quả khác, behavioral compatibility có thể bị phá.

Không nên giả định thêm field optional luôn an toàn. Một client có thể deserialize strict hoặc dùng default khác. Compatibility phải xét consumer thật và semantics của field.

## 7. Thay đổi syntax có thể giữ semantics

Một thay đổi grammar có thể chỉ thay cách viết:

Cú pháp cũ:

~~~text
rule "active-customer" {
    if customer.active then allow()
}
~~~

Cú pháp mới:

~~~text
rule "active-customer" {
    when customer.active
    then allow()
}
~~~

Nếu cả hai được chuyển thành cùng một canonical AST và runtime semantics không đổi, đây có thể là syntax migration tương thích.

Cách kiểm chứng:
1. Parse source cũ bằng parser cũ.
2. Parse source mới sau migration.
3. Chuyển cả hai về canonical semantic representation.
4. So sánh semantics.
5. Chạy cùng input trên runtime và so sánh observable result.
6. Giữ source mapping và diagnostics cần thiết.

Text diff có thể lớn dù semantics không đổi. Ngược lại, một thay đổi một ký tự có thể đổi behavior đáng kể.

## 8. Thay đổi cấu trúc có thể làm đổi semantics

Một schema có thể đổi shape nhưng vẫn có migration giữ ý nghĩa. Ví dụ field:

~~~text
address: String
~~~

được tách thành:

~~~text
address: Address {
    line1: String
    city: String
    postalCode: String
}
~~~

Nếu migration ánh xạ đúng dữ liệu cũ và consumer được cập nhật, ý nghĩa có thể được bảo toàn. Nhưng nếu hệ thống trước đây dùng toàn bộ address như một chuỗi hiển thị, cấu trúc mới có thể thay đổi formatting, search hoặc matching.

Structural migration cần kiểm tra:
- Dữ liệu cũ ánh xạ sang field mới.
- Field thiếu được xử lý ra sao.
- Default có làm thay đổi kết quả không.
- Consumer nào dùng field cũ.
- Serialization và database mapping.
- Query/filter semantics.
- Generated API và client.

## 9. Thay đổi toán tử và biểu thức

Các toán tử thường có semantics tinh tế:
- Integer division và decimal division.
- Overflow.
- Equality giữa các kiểu khác nhau.
- So sánh null.
- Short-circuit evaluation.
- Operator precedence.
- String concatenation.
- Date arithmetic.
- Floating-point comparison.
- Collection membership.

Ví dụ:

~~~text
result = 5 / 2
flag = optionalValue == null
allowed = user.active and account.open
~~~

Nếu DSL đổi phép chia từ integer sang decimal, đổi null comparison hoặc không còn short-circuit, chương trình cũ có thể thay đổi output hoặc phát sinh lỗi mới.

Để tránh ambiguity, language spec nên định nghĩa rõ:
- Operand types.
- Result type.
- Conversion rules.
- Evaluation order.
- Error conditions.
- Null behavior.
- Overflow and precision policy.

## 10. Null semantics và optional values

Null là một trong những nguồn thay đổi ngữ nghĩa phổ biến. DSL có thể dùng:
- Two-valued logic: true/false.
- Three-valued logic: true/false/unknown.
- Optional type: Some/None.
- Null propagation.
- Null coalescing.
- Default-on-missing.

Ví dụ:

~~~text
when customer.age >= 18
then allow()
~~~

Nếu age là null, phiên bản cũ có thể trả unknown và rule không match. Phiên bản mới có thể ném exception hoặc coi null là false. Cả ba hành vi đều khác nhau đối với consumer.

Cần phân biệt:
- Field không xuất hiện.
- Field có giá trị null.
- Field có giá trị default.
- Field có optional wrapper không chứa giá trị.

Migration không nên tự động thay null bằng 0 hoặc chuỗi rỗng nếu các giá trị đó có ý nghĩa nghiệp vụ riêng.

## 11. Type conversion và numeric precision

Type system có thể thay đổi cách chuyển đổi:
- Implicit widening/narrowing.
- Decimal scale.
- Rounding mode.
- Integer overflow.
- Float/Double promotion.
- String-to-number coercion.
- Date/time conversion.

Ví dụ, chuyển Decimal có scale 3 thành scale 2 có thể:
- Reject.
- Round HALF_UP.
- Round HALF_EVEN.
- Truncate.
- Giữ scale động.

Mỗi lựa chọn có thể ảnh hưởng tiền, thuế hoặc số liệu. Semantics cần được định nghĩa tường minh và có test tại giá trị biên.

Với phép tính tài chính, cần cân nhắc decimal arithmetic và currency unit. Không nên đổi từ exact decimal sang binary floating point mà không đánh giá sai số và compatibility.

## 12. Time, timezone và lịch nghiệp vụ

Thời gian là một phần của semantics, không chỉ là định dạng. Cần phân biệt:
- LocalDate.
- LocalDateTime.
- Instant.
- ZonedDateTime.
- Duration.
- Period.
- Business calendar.

Ví dụ “30 ngày sau” có thể là duration 30 × 24 giờ hoặc một ngày lịch sau 30 ngày theo timezone. Hai cách khác nhau quanh daylight saving transition.

Nếu runtime mới đổi timezone mặc định từ local host sang UTC, một rule effective date có thể kích hoạt vào thời điểm khác. Cần inject timezone và clock, tránh dựa vào cấu hình máy.

Migration thời gian cần kiểm tra các boundary:
- Trước thời điểm hiệu lực.
- Đúng thời điểm hiệu lực.
- Ngay sau thời điểm hiệu lực.
- Ngày chuyển DST.
- Cuối tháng/năm.
- Leap day.
- Khoảng valid time chồng lấn.

## 13. Thứ tự đánh giá và side effects

Một DSL rule hoặc workflow có thể có nhiều bước. Thứ tự thực thi có thể là một phần contract nếu các bước có side effect hoặc phụ thuộc trạng thái.

Ví dụ:

~~~text
workflow "checkout" {
    validateInventory()
    reserveItems()
    chargePayment()
    createShipment()
}
~~~

Nếu phiên bản mới charge payment trước reserve inventory, failure path có thể để lại giao dịch thanh toán mà không có hàng được giữ.

Cần xác định:
- Các bước có thuần (pure) hay có side effect.
- Thứ tự có được bảo đảm không.
- Có transaction boundary không.
- Compensation khi bước sau thất bại.
- Retry và idempotency.
- Event được phát trước hay sau commit.
- Cancellation semantics.

Thay đổi scheduling hoặc parallelism cũng có thể thay behavior nếu action không độc lập.

## 14. Rule priority và conflict resolution

Trong rule engine, nhiều rule có thể cùng match. Semantics phụ thuộc:
- Priority/salience.
- Thứ tự khai báo.
- First-match hay all-match.
- Rule firing strategy.
- Conflict resolution.
- Kết quả có thể ghi đè nhau không.
- Có lặp đến fixed point không.

Ví dụ:

~~~text
rule "vip-discount" priority 20 {
    when customer.vip
    then discount = 0.15
}

rule "campaign-discount" priority 10 {
    when campaign.active
    then discount = 0.10
}
~~~

Nếu runtime mới thay đổi tie-break hoặc thứ tự firing, kết quả có thể khác dù source và rule priority không đổi.

Một test tương thích cần tạo input khiến nhiều rule cùng match và xác minh kết quả, trace và side effect. Chỉ test từng rule riêng lẻ sẽ không phát hiện conflict semantics.

## 15. Query semantics và thứ tự kết quả

DSL query có thể thay đổi:
- Null ordering.
- Collation.
- Case sensitivity.
- Join cardinality.
- Duplicate elimination.
- Grouping equality.
- Aggregate empty-set behavior.
- Pagination stability.
- Time-window boundaries.

Ví dụ query không có ORDER BY thường không bảo đảm thứ tự. Nếu consumer phụ thuộc thứ tự ngẫu nhiên, đó là dependency vào behavior chưa được cam kết. Nhưng nếu DSL công bố sort mặc định, thay đổi default sort là semantic change.

Với pagination, tie-breaking không ổn định có thể làm bản ghi trùng hoặc thiếu giữa các trang. Cần định nghĩa stable ordering khi contract yêu cầu.

## 16. Default values và normalization

Default và normalization có thể thay đổi semantics ngay cả khi source/request không đổi.

Ví dụ:
- Default timezone đổi.
- Default page size đổi.
- Missing boolean trước đây là false, nay là true.
- Chuỗi được trim trước khi so sánh.
- Identifier được lowercase.
- Currency mặc định thay đổi.

Một default mới có thể ảnh hưởng client cũ vốn không gửi field đó. Một normalization mới có thể gộp hai giá trị trước đây phân biệt.

Cần version hóa default và normalization rules, đồng thời kiểm tra input cũ. Nếu cần giữ behavior cũ cho client version cũ, có thể dùng API version hoặc compatibility adapter.

## 17. Error semantics và failure behavior

Consumer có thể dựa vào loại lỗi, mã lỗi hoặc khả năng retry. Thay đổi từ validation error sang server error, từ synchronous exception sang async failure hoặc từ 409 sang 400 đều có thể phá contract.

Cần xem:
- Error code.
- HTTP status hoặc event outcome.
- Retryable/non-retryable classification.
- Error path/source location.
- Partial side effect trước lỗi.
- Transaction rollback.
- Timeout và cancellation.
- Error message có ổn định hay không.

Message text thường không nên là contract machine-readable. Mã lỗi ổn định và structured details phù hợp hơn. Tuy nhiên, việc đổi error code cũng có thể phá client xử lý theo code.

## 18. Data semantics và schema evolution

Schema có thể giữ kiểu nhưng đổi ý nghĩa field. Ví dụ:
- amount chuyển từ gross sang net.
- status đổi nghĩa của một enum.
- createdAt chuyển timezone representation.
- duration chuyển từ milliseconds sang seconds.
- weight chuyển đơn vị gram sang kilogram.

Những thay đổi này rất nguy hiểm vì dữ liệu vẫn parse và lưu được. Có thể cần:
- Rename field để làm rõ semantics.
- Tạo field mới.
- Gắn unit vào type.
- Version hóa schema.
- Migration dữ liệu.
- Dual-read/dual-write có thời hạn.
- Backfill và reconciliation.
- Contract test cho consumer.

Không nên đổi đơn vị tại chỗ mà không migration dữ liệu và consumer.

## 19. Behavioral equivalence

Hai phiên bản tương đương về hành vi trong một phạm vi khi với cùng input, context và external facts, chúng tạo ra cùng observable outputs và side effects theo contract.

Có thể biểu diễn khái niệm:

~~~text
For all supported inputs x and contexts c:

observe(run(oldVersion, x, c))
    ==
observe(run(newVersion, x, c))
~~~

Trong thực tế không thể kiểm tra mọi input. Có thể dùng:
- Golden tests.
- Regression fixtures.
- Property-based tests.
- Differential testing.
- Model-based testing.
- Production shadow evaluation.
- Formal reasoning cho subset nhỏ.

Cần xác định observation gồm gì: output, database state, events, errors, ordering, audit trace hoặc latency class. Nếu chỉ so sánh response body mà bỏ side effect, test có thể bỏ sót thay đổi quan trọng.

## 20. Differential testing

Differential testing chạy cùng input trên hai version rồi so sánh kết quả.

Quy trình:
1. Chọn fixture và production-like sample đã được làm sạch.
2. Resolve cùng external facts hoặc snapshot.
3. Chạy version cũ.
4. Chạy version mới.
5. Chuẩn hóa phần không ổn định.
6. So sánh outputs, errors, side effects và traces.
7. Phân loại khác biệt.
8. Xác nhận khác biệt dự kiến hoặc sửa regression.

Ví dụ report:

| Scenario | Version A | Version B | Phân loại |
|---|---|---|---|
| Amount dưới ngưỡng | APPROVE | APPROVE | Unchanged |
| Amount tại biên | REVIEW | APPROVE | Changed |
| Missing income | REJECT | REVIEW | Changed |
| Null customer tier | No match | Error | Potential regression |

Differential testing không tự biết khác biệt đúng hay sai. Nó cung cấp evidence để reviewer đối chiếu với mục tiêu migration.

## 21. Metamorphic và property-based testing

Khi không có expected output cho mọi input, có thể kiểm tra quan hệ phải luôn đúng.

Ví dụ property:
- Nếu quantity tăng và mọi yếu tố khác giữ nguyên, total không giảm.
- Normalize hai lần bằng cùng policy cho kết quả như normalize một lần.
- Parse/serialize round trip giữ semantic model.
- Thêm comment không đổi evaluation result.
- Đổi tên local variable không đổi output.
- Reordering independent declarations không đổi semantics nếu DSL không cam kết thứ tự.
- Chạy cùng input và cùng context trên cùng version tạo kết quả xác định.

Metamorphic test đặc biệt hữu ích khi chuyển compiler hoặc optimizer, vì có thể so sánh các biến thể tương đương của source.

Cần tránh giả định property không được contract bảo đảm. Ví dụ reorder declarations chỉ là semantics-preserving nếu DSL định nghĩa declarations không phụ thuộc thứ tự.

## 22. Canonical intermediate representation

Một cách hỗ trợ semantic compatibility là chuyển source của nhiều phiên bản về một canonical intermediate representation (IR).

~~~mermaid
flowchart TD
    A[DSL v1 source] --> B[Parser v1]
    C[DSL v2 source] --> D[Parser v2]
    B --> E[Canonical IR]
    D --> E
    E --> F[Semantic analysis]
    F --> G[Runtime or generator]
~~~

Canonical IR có thể chuẩn hóa:
- Name resolution.
- Type identity.
- Default values.
- Operator representation.
- Source mapping.
- Nullability.
- Dependency references.
- Explicit evaluation policy.

Nếu hai syntax version tạo cùng canonical IR, có bằng chứng mạnh rằng khác biệt chỉ nằm ở cách biểu diễn. Tuy nhiên, IR cần giữ đủ semantics; nếu làm mất timezone, unit hoặc evaluation order, phép so sánh có thể sai.

Canonical IR cũng cần version hóa. Thay đổi schema IR có thể ảnh hưởng plugin, cache và artifact consumer.

## 23. Semantic diff

Text diff cho biết ký tự nào thay đổi. Semantic diff mô tả ý nghĩa thay đổi.

Ví dụ:

~~~diff
- when score > 70
+ when score >= 70
~~~

Semantic diff có thể nêu:
- Rule giờ match cả giá trị biên 70.
- Miền điểm được chấp nhận mở rộng tại biên.
- Quyết định với score bằng 70 có thể thay đổi.

Semantic diff có thể phát hiện:
- Field type hoặc nullability thay đổi.
- Default value thay đổi.
- Operator semantics thay đổi.
- Rule priority thay đổi.
- API response field mới hoặc mất.
- Unit đổi.
- Dependency version thay đổi.
- Timezone/effective date thay đổi.
- Error behavior thay đổi.

Semantic diff không thay thế review. Nó giúp người review tập trung vào hành vi bị ảnh hưởng thay vì đọc toàn bộ generated text.

## 24. Compatibility classification

Có thể phân loại thay đổi theo mức độ:

| Loại thay đổi | Ví dụ | Đánh giá ban đầu |
|---|---|---|
| Editorial | Comment, formatting | Thường không đổi semantics |
| Additive syntax | Thêm construct mới không xung đột | Có thể tương thích |
| Additive schema | Thêm field optional | Cần kiểm tra consumer |
| Restrictive | Tăng min hoặc giảm max | Có thể breaking |
| Type change | Integer sang Decimal | Cần migration |
| Default change | Missing field có default mới | Semantic breaking tiềm tàng |
| Behavior change | Null hoặc operator semantics đổi | Breaking nếu consumer dựa vào behavior cũ |
| Removal | Xóa function/field/rule | Thường breaking |
| Unit change | Millisecond sang second | Breaking và cần data migration |
| Runtime change | Evaluation order khác | Có thể thay output/side effect |

Đây là phân loại ban đầu, không phải quyết định tuyệt đối. Một thay đổi restrictive có thể an toàn nếu domain invariant vốn đã cấm dữ liệu đó; một additive field có thể phá client strict schema.

## 25. Migration có bảo toàn semantics

Migration là quá trình chuyển source, schema, data hoặc artifact sang version mới. Migration bảo toàn semantics khi ý nghĩa được giữ trong phạm vi mục tiêu.

Một quy trình:
1. Xác định source version và target version.
2. Parse bằng grammar nguồn.
3. Chuyển sang AST/IR có đủ thông tin.
4. Áp dụng transformation có quy tắc.
5. Sinh source hoặc artifact mới.
6. Chạy syntax/type validation.
7. So sánh semantic representation.
8. Chạy differential và regression tests.
9. Review các trường hợp không tự động chuyển được.
10. Ghi migration provenance.

Ví dụ chuyển function cũ sang function mới:

~~~text
old:
  isBefore(dateA, dateB)

new:
  dateA < dateB
~~~

Chuyển đổi chỉ an toàn nếu toán tử < có cùng null, timezone và ordering semantics với isBefore. Nếu không, migration phải giữ function adapter hoặc yêu cầu người dùng quyết định.

## 26. Migration tự động và migration cần review

Có thể tự động migration khi:
- AST transformation xác định.
- Có equivalence rule rõ.
- Không mất thông tin.
- Không thay đổi observable behavior.
- Test coverage đủ cho construct.

Cần review thủ công khi:
- Có ambiguous construct.
- Default hoặc unit thay đổi.
- Rule conflict semantics không tương đương.
- External function không có adapter.
- Data không đủ để suy ra giá trị mới.
- Side effect hoặc transaction behavior thay đổi.

Migration tool nên báo warning và vị trí source thay vì tự chọn một interpretation không có căn cứ.

## 27. Adapter và compatibility layer

Một compatibility adapter cho phép consumer cũ dùng contract cũ trong khi core đã chuyển sang API mới.

Ví dụ:
- API adapter chuyển field cũ thành model mới.
- Runtime adapter chuyển old IR sang current IR.
- Plugin adapter ánh xạ extension interface cũ.
- Schema adapter chuyển unit hoặc enum.
- DSL compatibility module giữ built-in cũ.

Adapter nên:
- Có version và lifecycle.
- Có test tương đương.
- Ghi rõ deprecated status.
- Có telemetry để biết còn consumer nào dùng.
- Có kế hoạch loại bỏ.
- Không âm thầm đổi semantics.

Adapter quá lâu có thể tạo nhiều nhánh behavior và tăng chi phí bảo trì. Nên có migration window và sunset policy.

## 28. Dual-read, dual-write và data migration

Khi schema thay đổi, có thể cần giai đoạn chuyển tiếp:
- **Dual-read:** đọc field mới, nếu không có thì đọc field cũ.
- **Dual-write:** ghi cả field cũ và mới trong thời gian migration.
- **Backfill:** chuyển dữ liệu cũ sang cấu trúc mới.
- **Reconciliation:** so sánh hai representation.
- **Cutover:** chuyển consumer sang field mới.
- **Retirement:** ngừng field cũ sau khi xác nhận không còn sử dụng.

Ví dụ đổi đơn vị duration từ milliseconds sang seconds. Không nên chỉ đổi tên field và chia số ở runtime nếu dữ liệu cũ đã được lưu. Cần migration dữ liệu có thể kiểm chứng, tránh nhân/chia hai lần.

Dual-write tạo nguy cơ hai bản dữ liệu lệch nhau. Cần xác định source of truth, transaction boundary và cách repair nếu một write thất bại.

## 29. Rollout và compatibility window

Một thay đổi semantic có thể được triển khai theo nhiều bước:

1. Phát hành runtime hiểu cả version cũ và mới.
2. Deploy adapter hoặc schema support.
3. Chạy migration và compatibility tests.
4. Shadow-evaluate version mới.
5. Canary cho một nhóm consumer.
6. Theo dõi output và lỗi.
7. Mở rộng rollout.
8. Chuyển default/active version.
9. Deprecate version cũ.
10. Loại bỏ sau compatibility window.

Không nên bật semantics mới ngay khi code mới được deploy nếu nhiều instance hoặc consumer chưa được nâng cấp. Version resolver hoặc feature flag có thể giúp pin behavior theo tenant, API version hoặc workflow.

## 30. Shadow evaluation và production comparison

Shadow evaluation chạy version mới với cùng input/context nhưng không dùng kết quả mới để tạo side effect chính thức. Nó giúp đo tác động trên dữ liệu thực tế đã được kiểm soát.

Cần:
- Cố định input snapshot.
- Dùng cùng external facts.
- Ngăn side effect của bản shadow.
- Gắn version và correlation ID.
- So sánh decision/output.
- Phân loại khác biệt.
- Bảo vệ dữ liệu nhạy cảm.
- Giới hạn tải thêm lên hệ thống.

Shadow result không nên được coi là bằng chứng đầy đủ nếu môi trường khác production hoặc thiếu dependency thật. Nhưng nó có thể phát hiện case hiếm mà fixture không bao phủ.

## 31. Version pinning và reproducibility

Để tái hiện một kết quả, cần pin:
- DSL language version.
- Compiler/generator version.
- Runtime version.
- Ruleset/schema version.
- Plugin/extension versions.
- Dependency artifacts.
- Configuration.
- External facts hoặc reference data snapshot.
- Evaluation time/timezone.

Nếu chỉ lưu DSL source nhưng dùng runtime mới, kết quả có thể khác do semantic change. Một manifest hoặc lockfile giúp cố định tổ hợp version.

Decision record nên lưu version đã resolve thực tế thay vì chỉ ghi alias như latest. Build artifact cũng nên chứa provenance để biết nó được tạo bởi compiler và plugin nào.

## 32. Semantic compatibility trong plugin ecosystem

Plugin có thể giữ nguyên interface binary nhưng thay hành vi. Ví dụ generator cũ sắp xếp field alphabetically; plugin mới giữ declaration order. Consumer có thể dựa vào output order hoặc golden files.

Compatibility contract của extension cần mô tả:
- Input model semantics.
- Output artifact semantics.
- Ordering.
- Error behavior.
- Thread safety.
- Side effects.
- Determinism.
- Lifecycle.
- Runtime dependencies.

Plugin manager chỉ xác nhận version range không đủ. Có thể cần contract tests chạy plugin với host API và fixture model đại diện.

Khi extension point thay đổi semantics, host có thể cung cấp adapter hoặc tăng extension point version độc lập với plugin package version.

## 33. Semantic compatibility trong query và database

Query DSL có thể sinh SQL hoặc truy vấn qua nhiều backend. Hai backend có thể khác semantics:
- Null comparison.
- String collation.
- Case sensitivity.
- Decimal arithmetic.
- Date/time functions.
- JSON extraction.
- Empty aggregate.
- Limit/offset ordering.
- Transaction isolation.

Một query được chuyển từ PostgreSQL sang SQL Server có thể parse và chạy nhưng trả kết quả khác do collation hoặc null ordering.

Cần:
- Định nghĩa semantic subset chung.
- Ghi rõ feature backend-specific.
- Test cùng fixture trên từng backend được hỗ trợ.
- Tránh giả định SQL dialects tương đương.
- Dùng conformance suite cho provider.
- Báo unsupported feature thay vì giả lập sai.

## 34. Semantic compatibility của generated API và client

Generated API có thể giữ endpoint và field nhưng thay:
- Status code.
- Error mapping.
- Default.
- Pagination.
- Sorting.
- Validation timing.
- Idempotency.
- Null serialization.
- Date/time format.

Generated client có thể deserialize response mới nhưng ứng dụng vẫn hiểu sai ý nghĩa field. Cần contract test và semantic documentation, đặc biệt khi enum, unit hoặc default thay đổi.

Một client generator nên tạo code và metadata version rõ. API schema nên thể hiện constraints có thể biểu diễn; domain rules không thể encode hoàn toàn cần được tài liệu hóa riêng.

## 35. Observability cho thay đổi ngữ nghĩa

Khi rollout version mới, cần theo dõi:
- Tỷ lệ decision thay đổi.
- Error code distribution.
- Validation failure rate.
- Latency và timeout.
- Database constraint violation.
- Retry và dead-letter count.
- Output artifact differences.
- Plugin initialization failures.
- Cache hit/miss.
- Consumer version distribution.

Metric cần gắn version ID để so sánh đúng. Nếu không biết request dùng ruleset nào, khó giải thích thay đổi kết quả.

Không nên log toàn bộ input nhạy cảm để so sánh. Có thể dùng synthetic sample, hash, aggregate statistics hoặc redacted trace theo policy.

## 36. Ví dụ: thay đổi semantics của phép tính giá

Giả sử phiên bản DSL cũ tính giá sau thuế bằng:

~~~text
total = subtotal * (1 + taxRate)
~~~

Phiên bản mới dùng quy tắc làm tròn tiền tệ sau mỗi dòng thay vì chỉ làm tròn tổng cuối.

Hai công thức có thể khác kết quả vài đơn vị nhỏ khi có nhiều dòng. Syntax và type vẫn không đổi, nhưng semantics về rounding thay đổi.

Quy trình migration:
1. Ghi rõ rounding mode và rounding boundary.
2. Tạo fixture có một dòng, nhiều dòng và giá trị biên.
3. Chạy version cũ và mới trên cùng input.
4. Phân tích các chênh lệch.
5. Xác nhận thay đổi theo chính sách nghiệp vụ.
6. Version hóa rule hoặc DSL behavior.
7. Shadow evaluation trên sample đã làm sạch.
8. Rollout theo nhóm.
9. Lưu version đã dùng trong invoice/decision record.
10. Không tính lại hóa đơn lịch sử bằng semantics mới nếu policy không yêu cầu.

Ví dụ cho thấy compatibility không thể suy ra từ chữ ký hàm hoặc schema.

## 37. Ví dụ Java: so sánh kết quả hai phiên bản

Một harness khái niệm có thể chạy cùng scenario trên hai runtime:

~~~java
record ObservedResult(
    Object value,
    String errorCode,
    List<DomainEvent> events
) {}

ObservedResult runScenario(
        RuleRuntime runtime,
        TestInput input) {

    TestEventCollector events = new TestEventCollector();

    try {
        Object value = runtime.evaluate(input, events);
        return new ObservedResult(value, null, events.events());
    } catch (RuleException ex) {
        return new ObservedResult(
            null,
            ex.code(),
            events.events()
        );
    }
}
~~~

Test:

~~~java
@Test
void newRuntimePreservesSupportedDecisionBehavior() {
    ObservedResult oldResult =
        runScenario(oldRuntime, fixtureInput());

    ObservedResult newResult =
        runScenario(newRuntime, fixtureInput());

    assertEquals(oldResult.value(), newResult.value());
    assertEquals(oldResult.errorCode(), newResult.errorCode());
    assertEquals(oldResult.events(), newResult.events());
}
~~~

Trong hệ thống thực tế, cần normalize các giá trị không ổn định như generated ID hoặc timestamp nếu chúng không thuộc contract. Không nên loại bỏ một khác biệt chỉ vì làm test khó pass; chỉ normalize khi contract nói giá trị đó không có ý nghĩa quan sát.

## 38. Quy trình quản lý semantic compatibility

Có thể áp dụng quy trình:

1. **Xác định consumer:** ai dùng source, schema, runtime hoặc artifact.
2. **Ghi behavioral contract:** output, error, ordering, time, side effect và guarantees.
3. **Phân loại thay đổi:** syntax, structure, type, default, behavior, data hoặc runtime.
4. **Tạo semantic diff:** nêu các behavior có thể đổi.
5. **Xác định compatibility scope:** backward, forward, source, binary, schema hay behavioral.
6. **Thiết kế migration:** AST transform, adapter, data backfill hoặc API version.
7. **Viết regression/equivalence tests:** dùng fixture và property.
8. **Chạy differential testing:** cùng input trên old/new.
9. **Kiểm tra external dependency:** plugin, database, backend và consumer.
10. **Shadow/canary rollout:** đo khác biệt trong phạm vi nhỏ.
11. **Theo dõi observability:** gắn version vào metric và trace.
12. **Pin provenance:** lưu version thực tế cho artifact và decision.
13. **Deprecate có thời hạn:** thông báo và theo dõi consumer cũ.
14. **Loại bỏ sau migration:** chỉ khi compatibility window đã kết thúc.

## 39. Những lỗi thường gặp

- Chỉ kiểm tra source parse được rồi kết luận tương thích.
- Coi giữ nguyên field name là giữ nguyên semantics.
- Thay đổi default mà không xét client cũ.
- Đổi unit nhưng không migration data.
- Không định nghĩa null và missing.
- Để timezone phụ thuộc máy chạy.
- Thay đổi ordering hoặc priority mà không test nhiều rule match.
- So sánh text output mà bỏ qua behavior.
- Dùng mock không phản ánh serialization hoặc protocol thật.
- Replay quyết định với runtime mới nhưng không pin external facts.
- Cache artifact không chứa compiler/plugin version.
- Shadow evaluation có side effect.
- Rollback code nhưng không xử lý data đã được ghi theo semantics mới.
- Giữ adapter vô thời hạn mà không có sunset plan.
- Không lưu version đã resolve trong audit/decision record.

## 40. Nguyên tắc thiết kế

- **Xem behavior là contract:** syntax và type signature chưa đủ để xác định compatibility.
- **Ghi rõ semantics:** null, default, unit, time, ordering, errors và side effects cần được định nghĩa.
- **Phân biệt các loại compatibility:** source, binary, schema, data, API, operational và behavioral.
- **Dùng canonical IR khi phù hợp:** so sánh semantics sau khi chuẩn hóa source.
- **Tạo semantic diff:** giải thích thay đổi hành vi thay vì chỉ hiển thị text diff.
- **Kiểm thử hai phiên bản trên cùng input:** differential và regression tests phát hiện khác biệt.
- **Dùng property/metamorphic tests:** kiểm tra invariant khi expected output không có sẵn.
- **Migration phải có căn cứ:** không tự suy đoán khi chuyển đổi không tương đương.
- **Adapter có thời hạn:** giữ consumer cũ trong compatibility window rồi loại bỏ có kiểm soát.
- **Pin mọi dependency quan trọng:** compiler, runtime, plugin, schema, ruleset và external facts.
- **Triển khai theo giai đoạn:** shadow, canary và rollout có quan sát.
- **Không replay side effect:** decision replay cần tách tính toán khỏi hành động bên ngoài.
- **Giữ provenance:** mỗi artifact và quyết định cần biết version thực tế đã dùng.
- **Test backend thực tế:** query, database và protocol có thể khác semantics.
- **Rollback phải xét dữ liệu:** quay code về version cũ không tự chuyển dữ liệu đã ghi.
- **Theo dõi behavior sau rollout:** metric và trace cần gắn version để phát hiện drift.

Tương thích ngữ nghĩa giúp một hệ thống DSL tiến hóa mà vẫn giữ được những cam kết mà source author, API consumer và runtime phụ thuộc. Khi contract hành vi được định nghĩa, thay đổi được phân loại bằng semantic diff, migration được kiểm chứng bằng differential và regression tests, version được pin và rollout được quan sát, hệ thống có thể thay đổi cú pháp, schema hoặc implementation mà vẫn kiểm soát được ý nghĩa của chương trình và dữ liệu qua nhiều thế hệ phiên bản.
