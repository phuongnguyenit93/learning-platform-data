# Thiết kế DSL theo hướng ví dụ

Một DSL (*Domain-Specific Language*) được tạo ra để giúp người dùng diễn đạt công việc trong một miền cụ thể. Nếu nhóm chỉ bắt đầu bằng grammar, AST hoặc type system, ngôn ngữ có thể phản ánh cấu trúc nội bộ của compiler nhiều hơn cách người dùng thực sự suy nghĩ và làm việc.

**Thiết kế hướng ví dụ** (*example-driven design*) là cách phát triển DSL bắt đầu từ những tình huống sử dụng cụ thể. Nhóm thu thập scenario, dữ liệu đầu vào và kết quả mong đợi; thử biểu diễn chúng bằng cú pháp dự kiến; sau đó rút ra vocabulary, grammar, semantics và type rules chung. Các ví dụ tiếp tục được mở rộng thành test fixtures và tài liệu chạy được.

Giả sử một nền tảng thương mại điện tử cần cho phép quản trị viên cấu hình ưu đãi. Các scenario ban đầu có thể là:

- Miễn phí giao hàng cho khách hàng Gold.
- Giảm 10% nếu tổng đơn hàng vượt ngưỡng.
- Không áp dụng ưu đãi cho sản phẩm bị loại trừ.
- Chuyển đơn hàng có rủi ro cao sang kiểm tra thủ công.

Từ những tình huống đó, nhóm nhận ra ngôn ngữ cần điều kiện, phép so sánh, toán tử logic, truy cập field, biểu thức số và kết quả quyết định.

Một biểu diễn có thể là:

```text
rule "gold-free-shipping" {
    when customer.membership == "gold"
    then shipping.fee = 0
}

rule "large-order-discount" {
    when order.total >= 1000000
    then order.discountRate = 0.10
}
```

Các ví dụ này không chỉ minh họa cú pháp. Chúng giúp xác định DSL có ý nghĩa gì, trường hợp nào hợp lệ, kết quả nào phải xảy ra và điều gì cần được kiểm thử.

## 1. Vì sao thiết kế hướng ví dụ hữu ích?

DSL là ngôn ngữ chuyên biệt cho một domain. Chất lượng của nó phụ thuộc vào việc người dùng có thể diễn đạt công việc thật một cách rõ ràng và an toàn.

Thiết kế hướng ví dụ giúp:

- Hiểu cách người dùng mô tả vấn đề trong domain.
- Phát hiện vocabulary và abstraction thực sự cần thiết.
- Tránh thêm syntax chỉ vì compiler dễ triển khai.
- Kiểm tra khả năng đọc trước khi grammar bị cố định.
- Phát hiện trường hợp biên và ambiguity sớm.
- Tạo ví dụ executable để làm regression tests.
- Giữ tài liệu, implementation và expected behavior nhất quán.
- Hỗ trợ review với chuyên gia nghiệp vụ không viết compiler.

Một grammar có thể đẹp về mặt hình thức nhưng không phù hợp với cách người dùng suy nghĩ. Ngược lại, một ví dụ trông tự nhiên có thể che giấu ambiguity hoặc semantics khó hiểu. Quy trình hướng ví dụ cho phép phát hiện cả hai trước khi đầu tư sâu vào implementation.

## 2. Ví dụ là điểm khởi đầu, không phải đặc tả hoàn chỉnh

Một ví dụ thể hiện một trường hợp cụ thể. Nó chưa nói hết các trường hợp tương tự.

Ví dụ:

```text
when order.total >= 1000000
then shipping.fee = 0
```

Ví dụ này chưa xác định:

- Nếu order.total bằng null thì sao?
- Nếu total là Decimal với scale khác nhau thì so sánh thế nào?
- Nếu nhiều rule cùng ghi shipping.fee thì rule nào thắng?
- Nếu condition sai thì có hành động nào không?
- Nếu field shipping.fee không tồn tại thì báo lỗi ở đâu?
- Assignment có xảy ra ngay hay chỉ tạo decision result?
- Có cho phép function call trong condition không?

Mỗi ví dụ cần được dùng để đặt câu hỏi và rút ra rule tổng quát. Sau đó bổ sung ví dụ khác để kiểm tra rule có đúng với nhiều trường hợp không.

### Example và counterexample

Một example minh họa behavior mong muốn. Một counterexample là trường hợp cho thấy một thiết kế hoặc giả định không đúng.

Nếu DSL cho phép mọi expression trong condition, hãy thử dùng một biểu thức trả String. Nếu type system không từ chối, có thể DSL chưa quy định điều kiện phải là Boolean.

Counterexample rất hữu ích vì chúng làm lộ các giả định ẩn.

## 3. Bắt đầu từ domain scenarios

Trước khi viết syntax, hãy thu thập các tình huống mà DSL cần hỗ trợ.

Nguồn scenario có thể gồm:

- Quy trình nghiệp vụ hiện tại.
- Spreadsheet hoặc rule table đang dùng.
- Form và cấu hình hiện hành.
- API hoặc command của hệ thống.
- Ticket và yêu cầu hỗ trợ.
- Quyết định do chuyên gia nghiệp vụ đưa ra.
- Quy tắc ngoại lệ và case thất bại.
- Các quy trình thủ công cần tự động hóa.

Mỗi scenario nên mô tả:

1. Bối cảnh.
2. Dữ liệu đầu vào.
3. Điều kiện hoặc quy tắc.
4. Kết quả mong đợi.
5. Ngoại lệ.
6. Người hoặc hệ thống chịu trách nhiệm.
7. Ràng buộc về quyền và thời gian.

Ví dụ một scenario xét duyệt đơn hàng:

```text
Scenario: Đơn hàng giá trị cao của khách hàng rủi ro thấp

Input:
  order.total = 12000000
  customer.risk = "low"

Expected:
  decision = "approve"

Exception:
  Nếu customer.risk chưa xác định, chuyển manual review.
```

Scenario này cung cấp input và expected behavior. Nhóm có thể dùng nó để thử nhiều cú pháp và xác định semantics của missing value.

## 4. Phân loại ví dụ theo mục đích

Không nên chỉ thu thập những ví dụ thành công đơn giản. Một tập ví dụ hữu ích thường có nhiều nhóm.

| Nhóm ví dụ | Mục đích | Minh họa |
|---|---|---|
| Happy path | Luồng thông thường | Rule đơn giản trả kết quả |
| Boundary | Giá trị sát ngưỡng | amount bằng min/max |
| Negative | Input không hợp lệ | Sai kiểu hoặc thiếu field |
| Edge case | Tình huống hiếm | Empty list, null, Unicode |
| Conflict | Nhiều rule cùng áp dụng | Hai rule ghi cùng field |
| Scale | Dữ liệu lớn | Hàng nghìn record |
| Security | Quyền bị giới hạn | Function không được cấp |
| Migration | Source cũ | Cú pháp deprecated |
| Integration | Tương tác hệ thống | Host function timeout |

Happy path giúp xác định cách dùng cơ bản. Boundary và negative cases giúp xác định semantics. Conflict và security cases giúp tìm giới hạn của mô hình.

## 5. Từ ví dụ tới vocabulary của DSL

Ngôn ngữ cần dùng từ vựng gần với domain mà người dùng hiểu.

Giả sử domain là quản lý đơn hàng. Người dùng có thể thường xuyên nói:

- Order.
- Customer.
- Shipping.
- Discount.
- Risk.
- Approval.
- Region.
- Threshold.

Các từ này có thể trở thành tên type, field, function hoặc construct.

Tuy nhiên, không phải thuật ngữ nghiệp vụ nào cũng cần thành keyword. Nên phân biệt:

- Keyword của ngôn ngữ.
- Identifier do người dùng đặt.
- Builtin function.
- Domain type.
- Field của data model.
- Label hoặc description chỉ phục vụ tài liệu.

Nếu mỗi khái niệm domain được biến thành keyword, grammar sẽ phình to và khó mở rộng. Thường nên giữ grammar nhỏ, còn vocabulary nghiệp vụ được thể hiện qua type, function, identifier và schema.

Ví dụ, thay vì tạo keyword riêng cho từng loại khách hàng, có thể dùng enum hoặc field:

```text
customer.segment == "gold"
customer.segment == "silver"
customer.segment == "standard"
```

Khi domain thêm segment mới, schema hoặc dữ liệu có thể mở rộng mà không cần sửa grammar.

## 6. Thiết kế ví dụ trước khi chọn syntax

Cùng một behavior có thể được biểu diễn bằng nhiều kiểu syntax.

Ví dụ điều kiện và kết quả:

```text
when order.total >= 1000000:
    outcome "freeShipping"
```

Hoặc dạng expression:

```text
if order.total >= 1000000 then "freeShipping" else "standardShipping"
```

Hoặc dạng rule:

```text
rule "free-shipping" {
    condition order.total >= 1000000
    result "freeShipping"
}
```

Để chọn, cần so sánh:

- Người dùng có đọc nhanh được không?
- Cú pháp có mở rộng khi thêm điều kiện không?
- Có thể biểu diễn nhiều statement không?
- Có rõ ràng về scope và precedence không?
- Có dễ viết formatter và editor support không?
- Có thể parse và báo lỗi tốt không?
- Có phù hợp với domain vocabulary không?

Đừng chọn syntax chỉ vì nó ngắn nhất. Cú pháp ngắn có thể thiếu chỗ biểu đạt metadata, error handling hoặc nested structure.

## 7. Dùng ví dụ để rút ra grammar

Khi đã có một nhóm ví dụ, hãy tìm cấu trúc lặp lại.

```text
rule "discount" {
    when order.total >= 1000000
    then order.discount = 0.1
}

rule "priority" {
    when customer.tier == "gold"
    then order.priority = true
}
```

Các điểm chung:

- Từ khóa rule.
- Tên rule.
- Block.
- Điều kiện when.
- Hành động then.
- Expression với field access.
- Literal và operator.

Từ đó có thể phác thảo grammar:

```text
Rule        ::= "rule" StringLiteral Block
Block       ::= "{" WhenClause ThenClause "}"
WhenClause  ::= "when" Expression
ThenClause  ::= "then" Statement
Expression  ::= ...
Statement   ::= ...
```

Đây chỉ là grammar khái niệm. Sau đó cần kiểm tra ambiguity, precedence, associativity, optional clauses và error recovery.

Một ví dụ đơn lẻ có thể khiến grammar quá chuyên biệt. Cần nhiều scenario có cùng cấu trúc nhưng khác dữ liệu, nested expression và ngoại lệ để tìm abstraction phù hợp.

## 8. Dùng ví dụ để xác định semantics

Sau grammar, cần xác định mỗi construct có nghĩa gì.

```text
when A and B then C
```

Cần quyết định:

- A được đánh giá trước B hay không?
- B có được bỏ qua khi A false không?
- C chỉ chạy khi cả hai true?
- Nếu A hoặc B unknown thì sao?
- Nếu C lỗi thì execution dừng hay tiếp tục?
- Nếu C có side effect, thứ tự được bảo đảm thế nào?

Các câu hỏi này là semantics, không phải syntax.

Một cách hữu ích là viết behavior thành bảng:

| A | B | Kết quả của A and B |
|---|---|---|
| true | true | true |
| true | false | false |
| false | true | false |
| false | false | false |

Nếu DSL hỗ trợ unknown/null, cần mở rộng bảng theo logic ba giá trị và ghi rõ cách xử lý.

## 9. Ví dụ executable như specification

Một ví dụ có thể được lưu cùng expected result và chạy tự động.

Ví dụ fixture:

```yaml
name: gold-customer-free-shipping
source: |
  when customer.segment == "gold":
      outcome "freeShipping"
input:
  customer:
    segment: gold
expected:
  outcome: freeShipping
```

Fixture này có thể được dùng bởi test runner để:

1. Parse source.
2. Validate type và symbol.
3. Tạo context.
4. Execute.
5. So sánh result.
6. Hiển thị diagnostics nếu khác expected.

Khi examples chạy trong CI, chúng trở thành executable specification. Nếu implementation thay đổi behavior ngoài ý muốn, test sẽ phát hiện.

Cùng fixture có thể được dùng trong documentation, tutorial, regression tests, compatibility tests, playground và demo trong IDE. Để tái sử dụng, cần có format fixture ổn định và tránh phụ thuộc vào dữ liệu bên ngoài không kiểm soát.

## 10. Golden examples và expected output

Golden test lưu output đã được review. Output có thể là:

- AST normalized.
- Type information.
- Diagnostic.
- Evaluation result.
- Generated source.
- Execution trace.
- Formatted DSL source.

Ví dụ:

```text
Input:
  2 + 3 * 4

Expected AST:
  Add(
    Integer(2),
    Multiply(Integer(3), Integer(4))
  )

Expected result:
  14
```

Golden output giúp reviewer nhìn thấy cách compiler hiểu ví dụ. Tuy nhiên, không nên cập nhật golden file tự động mà không xem diff và lý do. Nếu expected output được tạo từ chính implementation đang kiểm thử, bug có thể bị chấp nhận.

## 11. Thiết kế progressive examples

Một tutorial hoặc ví dụ thiết kế nên tăng độ phức tạp theo từng bước.

Một thứ tự hợp lý:

1. Literal và expression.
2. Biến và assignment.
3. Condition.
4. Function.
5. Collection.
6. Module và import.
7. Error handling.
8. Host integration.
9. Workflow hoặc policy hoàn chỉnh.

Ví dụ đầu tiên chỉ nên giới thiệu một construct. Ví dụ tiếp theo thêm một khả năng mới mà vẫn giữ ngữ cảnh quen thuộc.

Bước 1 – điều kiện đơn:

```text
when order.total >= 500000
```

Bước 2 – kết hợp điều kiện:

```text
when order.total >= 500000
     and customer.segment == "gold"
```

Bước 3 – thêm kết quả:

```text
when order.total >= 500000
     and customer.segment == "gold":
    outcome "freeShipping"
```

Bước 4 – xử lý trường hợp còn lại:

```text
when order.total >= 500000
     and customer.segment == "gold":
    outcome "freeShipping"
otherwise:
    outcome "standardShipping"
```

Progression này giúp người học hiểu mỗi construct mới giải quyết vấn đề nào.

## 12. Ví dụ đối chiếu và negative examples

Ví dụ tốt nên có cặp hợp lệ/không hợp lệ để làm rõ ranh giới.

Ví dụ hợp lệ:

```text
let total: Decimal = 125.50
```

Ví dụ không hợp lệ nếu DSL yêu cầu Decimal:

```text
let total: Decimal = "125.50"
```

Test nên xác nhận diagnostic rõ ràng, chẳng hạn expected Decimal but found String.

Negative examples giúp người dùng hiểu kiểu nào được phép, cú pháp nào không hợp lệ, vì sao compiler từ chối, cách sửa và trường hợp nào cần runtime check. Không nên chỉ đưa source sai mà không giải thích expected diagnostic.

## 13. Boundary examples và edge cases

Thiết kế từ ví dụ cần bao phủ biên của domain.

Ví dụ với discount threshold:

```text
when order.total >= 1000000:
    outcome "discount"
otherwise:
    outcome "regular"
```

Các input quan trọng:

| order.total | Expected |
|---:|---|
| 999999 | regular |
| 1000000 | discount |
| 1000001 | discount |
| 0 | regular |
| null | Theo null policy đã định |
| -1 | Theo domain validation |

Boundary examples giúp xác định operator, numeric type, null semantics và validation.

Empty collection, Unicode, overflow, timezone, duplicate rule và concurrent execution có thể làm lộ vấn đề thiết kế mà happy path không thể hiện.

## 14. Example matrix

Khi DSL có nhiều construct, một matrix giúp tránh chỉ tập trung vào vài ví dụ phổ biến.

| Feature | Basic | Boundary | Invalid | Interaction |
|---|---|---|---|---|
| Numeric expression | 2 + 3 | Max integer | Overflow | Decimal promotion |
| Condition | A and B | Unknown | String as Boolean | Short-circuit |
| Function | Simple call | Default arg | Wrong arity | Host function |
| Collection | List literal | Empty list | Wrong element type | Nested iteration |
| Module | Simple import | Cycle | Missing symbol | Alias collision |
| Rule | One match | No match | Invalid output | Multiple rules |

Matrix là công cụ tổ chức coverage của examples. Nó không thay thế test plan, nhưng giúp thấy feature nào chưa có tình huống đại diện.

## 15. Thiết kế theo ví dụ và user journey

Một ví dụ đơn lẻ kiểm tra một construct. Một user journey cho thấy người dùng thực hiện công việc từ đầu đến cuối.

Ví dụ journey tạo rule:

1. Người dùng mở editor.
2. Chọn domain schema.
3. Viết rule.
4. Nhận completion và diagnostics.
5. Chạy preview với input mẫu.
6. Xem decision trace.
7. Lưu draft.
8. Publish revision.
9. Theo dõi execution.
10. Rollback nếu có vấn đề.

Journey giúp nhận ra DSL cần thêm tooling hoặc lifecycle support chứ không chỉ grammar.

Cần thử ví dụ trong editor thật hoặc playground. Một syntax có vẻ tự nhiên trên tài liệu có thể khó nhập, khó format hoặc khó báo lỗi khi người dùng viết dở.

## 16. Thiết kế API và builtin từ ví dụ

Ví dụ sử dụng thường cho thấy builtin function nào cần có và API nào quá thấp cấp.

```text
let shipping = calculateShipping(order, destination)
let eligible = isEligibleForDiscount(customer, order)
```

Nếu người dùng phải viết lặp nhiều biểu thức phức tạp để tính một khái niệm nghiệp vụ phổ biến, có thể cần một builtin hoặc domain function.

Tuy nhiên, không nên thêm function chỉ để phục vụ một ví dụ hiếm. Hãy xem nhiều scenario và xác định abstraction ổn định.

Mỗi function cần xác định signature, input/output types, nullability, error behavior, side effects, required capabilities, performance constraints và versioning.

## 17. Thiết kế type system từ ví dụ dữ liệu

Data examples giúp xác định type system cần hỗ trợ những kiểu nào.

```text
Customer {
    id: UUID
    name: String
    membership: Membership
    joinedAt: DateTime
    creditLimit: Decimal?
}
```

Từ dữ liệu này, nhóm cần quyết định:

- Decimal có precision và scale không?
- DateTime có timezone không?
- Membership là enum hay string?
- creditLimit optional hay nullable?
- Field có thể vắng mặt trong input không?
- Record có immutable không?
- Field access không tồn tại được xử lý thế nào?

Một schema example có thể trở thành input cho type checking, serialization và documentation tests.

## 18. Thiết kế error messages từ ví dụ lỗi

Hãy tạo các ví dụ sai mà người dùng thực tế có thể viết.

```text
when order.total > "1000":
    outcome "discount"
```

Diagnostic nên cho biết vị trí lỗi, kiểu mong đợi, kiểu nhận được, construct liên quan và cách sửa nếu có thể xác định.

Ví dụ diagnostic:

```text
DSL-TYPE-014 at rules/discount.dsl:1:20
Cannot compare Decimal with String.
Use a Decimal literal or convert the input explicitly.
```

Thiết kế error message từ ví dụ lỗi giúp tránh diagnostics chỉ nói invalid expression mà không giúp người dùng sửa.

## 19. Dùng examples để phát hiện ambiguity

Một cú pháp có thể có nhiều cách parse.

```text
a - b - c
```

Nếu associativity không được quy định, biểu thức có thể được hiểu là (a - b) - c hoặc a - (b - c).

Một ví dụ khác:

```text
match value {
    case A | B => result
}
```

Ký hiệu | có thể là pattern alternative hoặc bitwise OR tùy vị trí và grammar.

Hãy dùng ví dụ đối chiếu để kiểm tra parser có một cách hiểu duy nhất. Nếu syntax quá mơ hồ, cần sửa grammar hoặc yêu cầu parentheses.

## 20. Thiết kế examples cho migration và versioning

Khi DSL phát triển, ví dụ cũ giúp xác định behavior cần giữ và cách chuyển đổi.

Ví dụ syntax cũ:

```text
legacyDate("2025-01-31")
```

Syntax mới:

```text
date("2025-01-31")
```

Migration example cần chỉ ra khi nào transformation tương đương và khi nào cần người dùng chọn timezone hoặc format.

Một codemod có thể biến đổi source, nhưng examples cần xác nhận output trước/sau cho các trường hợp đại diện. Trường hợp mơ hồ nên tạo diagnostic thay vì đoán.

Một ví dụ nên ghi language version hoặc runtime requirement nếu cú pháp chỉ có ở một phiên bản. Examples lịch sử cần được giữ theo version khi semantics thay đổi.

## 21. Examples as documentation và docs as tests

Tài liệu có thể chứa code block được chạy tự động. Mỗi example có thể được extract và compile hoặc execute trong CI.

Lợi ích:

- Phát hiện tài liệu lỗi thời.
- Xác nhận cú pháp còn hợp lệ.
- Đảm bảo expected output đúng.
- Hỗ trợ versioned documentation.
- Tạo playground sample từ cùng nguồn.

Cần đánh dấu loại block:

- Runnable example.
- Pseudocode.
- Output minh họa.
- Invalid example dùng để giải thích diagnostic.

Không nên tự động thực thi mọi code block vì có thể có pseudocode hoặc ví dụ có side effect.

## 22. Review ví dụ với chuyên gia domain

Chuyên gia nghiệp vụ có thể xác nhận behavior và vocabulary mà không cần đọc parser implementation.

Một buổi review có thể hỏi:

- Ví dụ có phản ánh công việc thật không?
- Kết quả mong đợi có đúng policy không?
- Thuật ngữ có tự nhiên không?
- Có ngoại lệ quan trọng nào bị bỏ sót?
- Có trường hợp người dùng hiểu syntax theo cách khác không?
- Một rule có thể gây tác động ngoài ý muốn không?

Review cần phân biệt ý kiến về nghiệp vụ với quyết định về syntax. Một chuyên gia có thể xác nhận rule đúng nhưng không nhất thiết chọn được grammar tốt nhất.

## 23. Ví dụ hướng tới an toàn và security

Examples cũng cần thể hiện giới hạn quyền.

Một rule đọc order có thể đơn giản:

```text
when order.total > 1000000:
    outcome "review"
```

Nếu chương trình cần gọi function đọc customer profile, ví dụ nên thể hiện capability được cấp hoặc giới hạn rõ. Không nên đưa vào tài liệu một ví dụ ngầm cho phép DSL truy cập mọi service hoặc filesystem.

Security examples có thể gồm function được phép và bị từ chối, tenant isolation, resource limit, timeout, input validation, safe error handling và không thực hiện side effect trong preview.

## 24. Quản lý example corpus

Khi số lượng ví dụ tăng, cần tổ chức thành corpus có thể tìm, version và tái sử dụng.

```text
examples/
  basics/
    expressions.dsl
    variables.dsl
  rules/
    discount.dsl
    shipping.dsl
  types/
    optional-fields.dsl
    union-types.dsl
  errors/
    wrong-type.dsl
    missing-symbol.dsl
  migration/
    v2-to-v3/
      before.dsl
      after.dsl
  integration/
    host-functions.dsl
```

Mỗi example có thể kèm metadata:

- ID.
- Feature.
- Language version.
- Expected result hoặc diagnostic.
- Có side effect không.
- Mức độ tin cậy của input.
- Nơi dùng trong documentation.
- Test owner.

Một corpus có cấu trúc giúp tránh copy cùng ví dụ vào nhiều nơi rồi mỗi bản dần khác nhau.

## 25. Example review và change process

Khi thêm syntax hoặc semantics, pull request nên kèm examples mới hoặc cập nhật examples hiện có.

Review có thể xem:

- Ví dụ có phản ánh use case không?
- Có happy path và boundary không?
- Expected output có được xác nhận độc lập không?
- Có test executable không?
- Có version metadata không?
- Có migration example nếu breaking không?
- Có negative example và diagnostic không?
- Có security implications không?

Nếu thay đổi không ảnh hưởng người dùng, có thể không cần thêm example công khai, nhưng vẫn nên có test phù hợp với implementation.

## 26. Những lỗi thường gặp khi thiết kế hướng ví dụ

**Chỉ dùng happy path.** Thiết kế bỏ sót null, boundary, invalid input và conflict. Thêm negative và edge examples.

**Để syntax dẫn dắt domain.** Ngôn ngữ có thể phản ánh cấu trúc compiler hơn là công việc người dùng. Bắt đầu từ scenario và vocabulary thật.

**Tổng quát hóa từ một ví dụ.** Grammar có thể quá chuyên biệt. Thu thập nhiều scenario trước khi chốt abstraction.

**Ví dụ không có expected result.** Không thể xác định behavior đúng. Ghi input và output hoặc diagnostic mong đợi.

**Examples không chạy trong CI.** Tài liệu và implementation dễ lệch. Biến runnable examples thành executable specification.

**Expected output được sinh từ cùng implementation.** Test có thể lặp lại bug. Dùng specification hoặc oracle độc lập.

**Không ghi language version.** Người dùng copy syntax không được hỗ trợ. Gắn version và runtime requirements.

**Dùng pseudocode như code thật.** Người đọc không biết block có thể chạy không. Đánh dấu loại ví dụ rõ.

**Không thử editor và formatter.** Syntax dễ đọc trên trang có thể khó nhập. Kiểm tra trong tooling thực tế.

**Không kiểm tra ambiguity.** Một ví dụ đơn giản có thể che giấu nhiều cách parse. Dùng expression đối chiếu và AST expectations.

**Sửa ví dụ lịch sử âm thầm.** Tài liệu version cũ mất giá trị. Giữ examples theo version hoặc ghi rõ thay đổi.

**Ví dụ có side effect nguy hiểm.** Người dùng chạy thử có thể tạo dữ liệu thật. Dùng fixture và environment an toàn.

## 27. Quy trình thiết kế DSL theo hướng ví dụ

Có thể triển khai theo trình tự:

1. Thu thập domain scenarios từ người dùng, quy trình và dữ liệu thật.
2. Mô tả input, expected behavior, ngoại lệ và constraints cho từng scenario.
3. Phân loại happy path, boundary, negative, conflict, security và integration cases.
4. Xác định vocabulary và domain concepts xuất hiện lặp lại.
5. Thử nhiều cách biểu diễn syntax cho cùng một behavior.
6. Review khả năng đọc với người dùng và chuyên gia domain.
7. Rút ra grammar và AST constructs từ các ví dụ có cấu trúc chung.
8. Định nghĩa semantics, type rules, evaluation order và error behavior.
9. Tạo executable fixtures với expected result hoặc diagnostics.
10. Thêm examples tăng dần độ phức tạp cho tutorial.
11. Kiểm tra ambiguity, Unicode, null, numeric boundary và side effects.
12. Dùng examples để kiểm tra formatter, language server và editor experience.
13. Gắn language version và migration examples.
14. Tổ chức corpus dùng chung cho documentation, tests và playground.
15. Yêu cầu examples được cập nhật khi thay đổi public syntax hoặc semantics.

## 28. Câu hỏi tự kiểm tra

1. Thiết kế hướng ví dụ là gì và vì sao phù hợp với DSL?
2. Vì sao một ví dụ không thể thay thế đặc tả semantics?
3. Domain scenario nên ghi những thành phần nào?
4. Happy path, boundary, negative và conflict examples có mục đích gì?
5. Làm thế nào rút ra vocabulary từ ví dụ mà không biến mọi thuật ngữ thành keyword?
6. Vì sao cần nhiều ví dụ trước khi chốt grammar?
7. Syntax alternatives nên được so sánh theo tiêu chí nào?
8. Ví dụ có thể giúp xác định evaluation order và null semantics ra sao?
9. Executable specification là gì?
10. Golden examples có thể lưu những loại output nào?
11. Progressive examples hỗ trợ người học như thế nào?
12. Negative examples nên cung cấp diagnostic và cách sửa ra sao?
13. Example matrix giúp phát hiện feature coverage thiếu như thế nào?
14. User journey giúp thiết kế tooling ngoài grammar ra sao?
15. Vì sao examples cần language version metadata?
16. Làm thế nào để chạy code examples trong documentation mà không thực thi pseudocode?
17. Chuyên gia domain nên review ví dụ ở những khía cạnh nào?
18. Example corpus cần metadata gì để tái sử dụng?
19. Làm thế nào phát hiện syntax ambiguity bằng ví dụ đối chiếu?
20. Hãy thiết kế một tập ví dụ cho DSL tính chiết khấu, gồm scenario, syntax, expected result, boundary, invalid case và migration.

Thiết kế hướng ví dụ giúp DSL bắt đầu từ công việc người dùng cần làm và phát triển thành một ngôn ngữ có quy tắc rõ ràng. Khi examples bao phủ cả trường hợp thông thường, ngoại lệ, lỗi và tích hợp, chúng trở thành cầu nối giữa domain, syntax, semantics, implementation, documentation và test suite.

