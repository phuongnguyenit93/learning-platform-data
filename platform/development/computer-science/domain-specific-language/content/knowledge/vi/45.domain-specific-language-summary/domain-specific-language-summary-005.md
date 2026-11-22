# Bài tập củng cố kiến thức về DSL

Các bài tập trong phần này giúp người học kết nối những khái niệm đã gặp khi tìm hiểu ngôn ngữ đặc tả miền (Domain-Specific Language, DSL): lựa chọn miền nghiệp vụ, thiết kế cú pháp, lexer, parser, AST, phân tích ngữ nghĩa, hệ kiểu, runtime, API, plugin, bảo mật, kiểm thử, đóng gói và quản trị vòng đời. Mục tiêu không chỉ là nhớ định nghĩa mà còn biết áp dụng chúng vào một bài toán có dữ liệu, quy tắc và người dùng cụ thể.

Có thể thực hiện các bài theo từng chủ đề hoặc dùng chúng như một mini-project liên tục. Với mỗi bài, hãy ghi giả định, ví dụ đầu vào, kết quả mong đợi và lý do chọn thiết kế. Nếu một câu hỏi có nhiều đáp án hợp lý, điều quan trọng là giải thích trade-off và nêu điều kiện khiến lựa chọn đó phù hợp.

## 1. Cách sử dụng bộ bài tập

### 1.1. Các mức độ

| Mức | Mục tiêu | Dạng bài |
|---|---|---|
| Nhận biết | Nhớ thuật ngữ và phân biệt khái niệm | Câu hỏi ngắn, so sánh |
| Vận dụng | Áp dụng một kỹ thuật vào ví dụ | Viết schema, token, AST |
| Phân tích | Tìm vấn đề và giải thích nguyên nhân | Debug, boundary, conflict |
| Thiết kế | Kết hợp nhiều thành phần | Thiết kế DSL và runtime |
| Đánh giá | So sánh trade-off và chọn phương án | Review kiến trúc, migration |
| Tổng hợp | Xây một lát cắt end-to-end | Mini-project |

### 1.2. Cách trình bày lời giải

Với bài thiết kế, lời giải nên có:
- Bối cảnh và giả định.
- Yêu cầu chức năng và phi chức năng.
- Mô hình dữ liệu hoặc cú pháp.
- Hành vi mong đợi.
- Trường hợp biên và lỗi.
- Cách kiểm thử.
- Hạn chế và lựa chọn thay thế.

### 1.3. Tự kiểm tra

Sau khi làm bài, hãy tự hỏi:
1. Kết quả có thể được một người khác tái hiện không?
2. Các thuật ngữ và semantics đã được định nghĩa chưa?
3. Có trường hợp thiếu dữ liệu hoặc nhiều rule cùng khớp không?
4. Có phân biệt code với data không?
5. Có test xác nhận cả kết quả và lỗi không?
6. Thiết kế có đang giải quyết đúng phạm vi đã chọn không?

## 2. Bài tập 1 — Phân biệt DSL và ngôn ngữ tổng quát

### Đề bài

Một nhóm muốn tạo cú pháp sau để mô tả điều kiện miễn phí vận chuyển:

~~~text
shippingPolicy {
    when order.total >= 1000000 VND
    then fee = 0 VND
}
~~~

Trả lời:
1. Vì sao đây có thể được xem là DSL?
2. Miền nghiệp vụ của nó là gì?
3. Người dùng mục tiêu là ai?
4. Nếu dùng Java hoặc Python để mô tả cùng quy tắc, ưu và nhược điểm là gì?
5. Trường hợp nào một file cấu hình đơn giản đủ tốt hơn một DSL?

### Gợi ý

Xem xét vocabulary, abstraction, syntax, semantics, người viết và loại thay đổi mà người dùng cần thực hiện. Không kết luận DSL tốt hơn chỉ vì cú pháp trông ngắn.

### Kết quả mong đợi

Một đoạn mô tả domain, persona, lợi ích và giới hạn. Nêu ít nhất hai lý do nên dùng DSL và hai lý do có thể không nên dùng.

## 3. Bài tập 2 — Chọn một miền nhỏ

### Đề bài

Chọn một trong các miền:
- Điều kiện miễn phí vận chuyển.
- Phân loại ticket hỗ trợ.
- Kiểm tra hồ sơ đăng ký.
- Điều kiện áp dụng khuyến mãi.
- Phê duyệt yêu cầu chi phí.

Viết project brief gồm:
1. Vấn đề cần giải quyết.
2. Người dùng và domain expert.
3. Bounded context.
4. In-scope và out-of-scope.
5. Năm thuật ngữ miền.
6. Ít nhất năm rule.
7. Input và output.
8. Ba trường hợp biên.
9. Tiêu chí thành công có thể kiểm chứng.

### Gợi ý

Thu hẹp phạm vi đến một quyết định hoặc quy trình. Không đưa thanh toán, notification hoặc tích hợp production vào nếu chúng không cần thiết để chứng minh DSL.

### Kết quả mong đợi

Một project brief đủ cụ thể để người khác hiểu DSL sẽ mô tả gì và cách xác nhận nó đúng.

## 4. Bài tập 3 — Xây dựng domain model

### Đề bài

Với miền miễn phí vận chuyển, hãy thiết kế:
- Entity.
- Value object.
- Enum.
- Relationship.
- Required và optional field.

Một schema gợi ý để bắt đầu:

~~~text
Customer {
    id: CustomerId
    tier: CustomerTier
}

Order {
    id: OrderId
    customerId: CustomerId
    total: Money
    region: RegionCode
    containsBulkyItem: Boolean
}
~~~

Bổ sung các kiểu cần thiết và giải thích:
1. Vì sao Money không nên chỉ là Decimal?
2. CustomerId và OrderId có nên cùng là String không?
3. RegionCode nên là enum hay string tự do?
4. Nếu customer tier không được cung cấp thì xử lý thế nào?
5. Quan hệ Customer-Order có cardinality gì?

### Gợi ý

Phân biệt hình thức biểu diễn với semantics. Hai giá trị cùng là chuỗi vẫn có thể là hai domain type khác nhau.

## 5. Bài tập 4 — Thiết kế rule và decision table

### Đề bài

Tạo rule cho chính sách sau:
- Đơn hàng từ 1.000.000 VND được miễn phí vận chuyển.
- Khách hàng PREMIUM được miễn phí vận chuyển.
- Hàng cồng kềnh có phụ phí 50.000 VND.
- Khu vực xa có phụ phí 30.000 VND.

Hãy:
1. Viết các rule bằng ngôn ngữ tự nhiên.
2. Chuyển thành decision table.
3. Xác định tình huống nhiều rule cùng khớp.
4. Đề xuất conflict resolution.
5. Định nghĩa no-match behavior.
6. Đưa ra năm test case với expected result.

### Gợi ý

Không tự giả định phụ phí có cộng với miễn phí hay không. Hãy nêu một policy rõ ràng, ví dụ miễn phí phần phí cơ bản nhưng phụ phí đặc biệt vẫn được tính, hoặc một rule ưu tiên quyết định toàn bộ phí.

### Kết quả mong đợi

Rule catalog, decision table, resolver policy và test cases có thể chạy được.

## 6. Bài tập 5 — Thiết kế lexical grammar

### Đề bài

DSL hỗ trợ:
- Keyword: rule, when, then, and, or, not.
- Identifier.
- Integer và decimal.
- String.
- Operator: ==, !=, <, <=, >, >=.
- Dấu ngoặc và dấu chấm.
- Line comment bắt đầu bằng //.

Hãy:
1. Viết lexical rule cho từng token.
2. Phân biệt keyword với identifier.
3. Giải thích maximal munch cho >= và >.
4. Xác định cách xử lý dấu âm.
5. Định nghĩa whitespace và newline.
6. Nêu cách xử lý comment cuối file không có newline.

### Gợi ý

Test keyword boundary bằng rule và ruleName. Xác định rõ dấu trừ là một token riêng hay một phần numeric literal.

### Kết quả mong đợi

Một token catalog có pattern, priority và ví dụ hợp lệ/không hợp lệ.

## 7. Bài tập 6 — Tokenize một đoạn source

### Đề bài

Cho source:

~~~text
rule PremiumDiscount {
    when customer.tier == PREMIUM and order.total >= 500000
    then discount = 0.10
}
~~~

Hãy liệt kê token stream theo thứ tự. Với mỗi token, ghi:
- Type.
- Lexeme.
- Literal value nếu có.
- Line và column.
- Source span.

Sau đó thay >= bằng > và giải thích token stream có gì thay đổi.

### Gợi ý

Chọn quy ước line/column và offset trước khi tính. Dùng khoảng span nửa mở để dễ kiểm tra.

### Kết quả mong đợi

Một token table đầy đủ, có EOF và vị trí chính xác.

## 8. Bài tập 7 — Phân tích cú pháp và AST

### Đề bài

Xét biểu thức:

~~~text
customer.active and (order.total >= 500000 or customer.tier == PREMIUM)
~~~

Hãy:
1. Viết grammar expression đơn giản.
2. Xác định precedence của and, or và comparison.
3. Vẽ hoặc mô tả AST.
4. Giải thích vì sao AST khác token stream.
5. Nêu diagnostic cho biểu thức thiếu dấu đóng ngoặc.

### Gợi ý

Một AST có thể là:

~~~text
And(
    Field("customer.active"),
    Or(
        GreaterEqual(Field("order.total"), Integer(500000)),
        Equal(Field("customer.tier"), EnumValue("PREMIUM"))
    )
)
~~~

Không cần giữ mọi dấu ngoặc trong AST nếu cấu trúc đã được biểu diễn bằng node. Nhưng source span vẫn hữu ích cho diagnostics.

## 9. Bài tập 8 — Semantic analysis và type checking

### Đề bài

Với schema:
~~~text
Customer {
    active: Boolean
    tier: CustomerTier
}

Order {
    total: Money
    quantity: Integer
}
~~~

Xác định biểu thức nào hợp lệ:
1. customer.active and order.quantity > 0
2. order.total > 100000 VND
3. customer.tier == PREMIUM
4. order.total + order.quantity
5. customer.active == "yes"
6. order.quantity >= 1.5

Với mỗi biểu thức, giải thích type checking và đề xuất diagnostic nếu sai.

### Gợi ý

Xét kiểu hai vế, operator được hỗ trợ, unit và implicit conversion. Không cho phép conversion ngầm nếu có thể làm mất ý nghĩa.

### Kết quả mong đợi

Bảng expression, inferred type, valid/invalid và diagnostic.

## 10. Bài tập 9 — Thiết kế kiểu kết quả

### Đề bài

Xác định kiểu kết quả cho các query:
1. Lấy tên của mọi Customer.
2. Tìm một Customer theo ID có unique constraint.
3. Đếm Order đã thanh toán.
4. Nhóm doanh thu theo Customer.
5. Lấy Customer cùng danh sách Order.
6. Stream tất cả Event theo thời gian.

Giải thích sự khác biệt giữa:
- String và List<String>.
- Customer và Optional<Customer>.
- Optional<List<Order>> và List<Optional<Order>>.
- List<T> và Stream<T>.
- Page<T> và CursorPage<T>.

### Gợi ý

Phân biệt kiểu phần tử, cardinality, nullability, ordering và evaluation strategy.

### Kết quả mong đợi

Một result type cho từng query cùng giải thích semantics.

## 11. Bài tập 10 — Thiết kế interpreter hoặc compiler

### Đề bài

Chọn một biểu thức:
~~~text
order.total >= 1000000 VND and customer.tier == PREMIUM
~~~

Mô tả pipeline:
1. Lexer tạo token.
2. Parser tạo AST.
3. Semantic analyzer kiểm tra field và type.
4. Compiler tạo IR hoặc interpreter evaluate AST.
5. Runtime nhận context.
6. Decision result được serialize.

Hãy nêu:
- Thành phần nào chạy một lần lúc compile?
- Thành phần nào chạy mỗi request?
- Diagnostic được tạo ở giai đoạn nào?
- Làm sao giữ source span trong AST?
- Khi schema thay đổi, artifact cần được xử lý ra sao?

### Gợi ý

Phân biệt compile-time artifact với runtime input. Không parse lại payload như DSL source.

## 12. Bài tập 11 — API payload và schema

### Đề bài

Thiết kế request/response cho endpoint đánh giá ShippingPolicy.

Request cần có:
- Order total.
- Currency.
- Customer tier.
- Region.
- Bulky flag.

Response cần có:
- Eligible.
- Final fee.
- Reason codes.
- Policy version.

Hãy xác định:
1. Kiểu từng field.
2. Required/optional/nullable.
3. Decimal precision.
4. Error payload.
5. Schema version.
6. Cách xử lý field không biết.
7. Cách phân biệt missing với null.

### Gợi ý

Money cần amount và currency. Reason code nên ổn định hơn message text. Client không được tự gửi policy version để ép server dùng phiên bản chưa được phép.

## 13. Bài tập 12 — Plugin và stable core

### Đề bài

Giả sử DSL có core hỗ trợ Boolean, Integer, Decimal, record và rule evaluation. Nhóm muốn bổ sung:
- Hàm tính thuế.
- Connector PostgreSQL.
- Validator workflow.
- Backend SQL.
- Formatter.

Phân loại từng chức năng vào core hay plugin và giải thích. Sau đó thiết kế một extension contract cho function provider.

### Gợi ý

Xét tính phổ quát, dependency, lifecycle, release cadence và capability. Core định nghĩa interface; plugin triển khai.

### Kết quả mong đợi

Bảng phân loại, dependency direction, interface và manifest mẫu.

## 14. Bài tập 13 — Phòng chống injection runtime

### Đề bài

Một API nhận sortField và filterValue rồi tạo SQL:

~~~java
String sql = "SELECT * FROM orders WHERE status = '" +
    filterValue + "' ORDER BY " + sortField;
~~~

Hãy:
1. Xác định hai vị trí có nguy cơ injection.
2. Viết lại bằng parameterized query.
3. Thiết kế allowlist cho sortField.
4. Giải thích vì sao parameter binding không áp dụng trực tiếp cho identifier.
5. Nêu cách giới hạn tenant scope.
6. Đề xuất test security cho input bất thường.

### Gợi ý

Giá trị filterValue cần bind. Identifier cần map từ enum hoặc allowlist server-side. Tenant ID nên lấy từ authenticated context.

### Kết quả mong đợi

Một query an toàn, policy cho identifier và bộ test negative.

## 15. Bài tập 14 — Kiểm thử tập luật

### Đề bài

Có ba rule:
- Premium customer được giảm 10%.
- Đơn hàng trên 2.000.000 VND được giảm 5%.
- Khách hàng bị khóa không được duyệt.

Thiết kế test gồm:
1. Một test cho từng rule.
2. Test biên ở 2.000.000 VND.
3. Test hai rule giảm giá cùng khớp.
4. Test khách hàng bị khóa nhưng là Premium.
5. Test không có rule khớp.
6. Property bất biến cho discount.
7. Decision trace mong đợi.

### Gợi ý

Xác định resolver trước khi viết expected result. Một kết quả cuối đúng chưa chắc trace đúng.

### Kết quả mong đợi

Test matrix có input, fired rule, expected decision và side effect.

## 16. Bài tập 15 — Kiểm thử lexer

### Đề bài

Viết test cho:
- Keyword boundary.
- Operator overlap.
- String escape.
- Unterminated string.
- Comment nhiều dòng.
- Unicode identifier.
- CRLF.
- EOF.
- Ký tự không hợp lệ.

Bổ sung hai property:
- Token span luôn nằm trong source.
- Lexer luôn tiến hoặc kết thúc.

Nếu có incremental lexer, so sánh output incremental với full lex sau một edit.

### Gợi ý

Kiểm tra type, lexeme, decoded value, span và diagnostics. Fuzz input malformed nhưng giới hạn thời gian và bộ nhớ.

## 17. Bài tập 16 — Đóng gói sản phẩm DSL

### Đề bài

Đóng gói ShippingPolicy DSL thành package có thể triển khai ở staging và production.

Hãy xác định:
1. Artifact cần đóng gói.
2. Manifest.
3. Runtime và plugin dependency.
4. Version và lockfile.
5. Configuration schema.
6. Secret management.
7. Checksum, signature và SBOM.
8. Clean install test.
9. Upgrade và rollback.
10. Release notes.

### Gợi ý

Tạo package một lần rồi promote cùng artifact qua môi trường. Endpoint và secret nằm trong cấu hình triển khai, không sửa package.

## 18. Bài tập 17 — Language ownership và lifecycle

### Đề bài

Một DSL được năm nhóm sử dụng nhưng hiện chỉ có một developer hiểu compiler và phát hành package.

Thiết kế mô hình ownership:
- Language Owner.
- Architect.
- Specification Maintainer.
- Runtime Maintainer.
- Security Owner.
- Release Manager.
- Domain Expert.

Định nghĩa:
1. Language charter.
2. Quy trình RFC.
3. Decision rights.
4. Versioning và compatibility policy.
5. Security response.
6. Deprecation window.
7. Succession plan.
8. End-of-life process.

### Gợi ý

Phân biệt người thực hiện và người chịu trách nhiệm cuối cùng. Tránh một cá nhân nắm mọi quyền release và kiến thức.

## 19. Bài tập 18 — Chọn kiến trúc và đánh giá trade-off

### Đề bài

Một DSL có thể chạy theo hai cách:
- Interpreter trực tiếp trên AST.
- Compiler tạo IR rồi runtime evaluate IR.

So sánh:
- Độ phức tạp triển khai.
- Startup và runtime performance.
- Diagnostics.
- Caching.
- Debugging.
- Compatibility.
- Plugin integration.
- Reproducibility.

Sau đó đề xuất lựa chọn cho:
1. DSL nhỏ chạy nội bộ.
2. DSL có nhiều request runtime.
3. DSL cần hỗ trợ nhiều backend.
4. DSL cho người dùng không tin cậy tạo rule.

### Gợi ý

Không có lựa chọn tốt nhất trong mọi trường hợp. Nêu giả định về workload, trust boundary và nhu cầu vận hành.

## 20. Bài tập tổng hợp — Xây một mini DSL end-to-end

### 20.1. Mục tiêu

Xây một DSL nhỏ để mô tả một chính sách có input, rule, output và test. Có thể dùng miền miễn phí vận chuyển, phân loại ticket hoặc kiểm tra hồ sơ.

### 20.2. Giai đoạn 1: Domain brief

Tạo:
- Problem statement.
- Persona.
- Bounded context.
- Glossary.
- In-scope/out-of-scope.
- Success criteria.

### 20.3. Giai đoạn 2: Domain model

Định nghĩa:
- Entity.
- Value object.
- Enum.
- Relationship.
- Input/output type.
- Nullability và constraint.

### 20.4. Giai đoạn 3: Language design

Định nghĩa:
- Token.
- Grammar.
- Operator precedence.
- Literal.
- Statement.
- Function call.
- Error behavior.

### 20.5. Giai đoạn 4: Implementation

Chọn interpreter hoặc compiler. Tạo lexer, parser, AST, semantic analyzer và runtime tối thiểu.

### 20.6. Giai đoạn 5: Test

Có:
- Lexer tests.
- Parser tests.
- Type tests.
- Rule tests.
- Boundary tests.
- Conflict tests.
- Security tests.
- Integration tests.

### 20.7. Giai đoạn 6: API

Tạo request/response schema, structured error và schema version. Kiểm tra serialization round-trip.

### 20.8. Giai đoạn 7: Extension

Nếu cần, tạo một plugin function hoặc validator. Core chỉ công bố interface và registry.

### 20.9. Giai đoạn 8: Packaging

Tạo manifest, khóa dependency, build artifact, checksum và hướng dẫn cài đặt. Thử clean install.

### 20.10. Giai đoạn 9: Governance

Ghi language owner, version policy, change process và support boundary.

### 20.11. Deliverables

Một mini-project có thể bàn giao:
- Domain brief.
- Glossary và model.
- Grammar reference.
- Source DSL examples.
- Lexer/parser implementation.
- AST hoặc IR.
- Runtime hoặc compiler.
- Test suite.
- API schema.
- Security notes.
- Package manifest.
- README và release notes.

## 21. Gợi ý đáp án và hướng suy luận

Phần này cung cấp hướng suy luận, không thay thế lời giải của từng nhóm.

### 21.1. Khi nào DSL có giá trị?

DSL có giá trị khi người dùng thường xuyên thay đổi một tập quy tắc có cấu trúc, cần review và giải thích, và cú pháp miền giúp giảm khoảng cách giữa ý định nghiệp vụ với implementation. Nếu chỉ có một cấu hình ít thay đổi, DSL có thể tạo thêm chi phí.

### 21.2. Miền nhỏ tốt

Một miền tốt có một decision boundary rõ, số entity vừa phải, vocabulary ổn định, dữ liệu đầu vào có thể mô phỏng và expected result có thể xác nhận.

### 21.3. Type safety

Strongly typed domain value như Money, CustomerId và RegionCode giúp ngăn nhầm lẫn giữa các scalar cùng hình thức. Decimal và unit cần semantics rõ.

### 21.4. Lexer và parser

Lexer nhận diện token. Parser tạo cấu trúc cú pháp. Semantic analyzer kiểm tra field, function và type. Runtime hoặc generated backend thực thi semantics.

### 21.5. Parameterization

Dữ liệu runtime phải đi qua parameter binding. Identifier động cần allowlist. Không ghép input vào DSL source hoặc SQL text.

### 21.6. Plugin boundary

Core định nghĩa stable contract; plugin phụ thuộc core API. Plugin manager kiểm tra manifest, version, capability và lifecycle. Core không import implementation plugin.

### 21.7. Test strategy

Kết hợp example-based, boundary, decision table, property-based, fuzz, regression và integration test. Coverage giúp đo phạm vi nhưng không chứng minh expected behavior đúng.

### 21.8. Packaging

Một package có manifest, artifact, dependency lock, config schema, documentation, checksum và provenance. Cùng artifact được promote qua môi trường bằng cấu hình bên ngoài.

### 21.9. Governance

Mọi DSL dùng chung cần owner, decision rights, spec source of truth, compatibility policy, release process, security contact và deprecation/EOL policy.

## 22. Tự đánh giá dự án

Sau khi hoàn thành mini-project, trả lời:
1. Miền đã chọn có đủ nhỏ và có giá trị không?
2. Người dùng có hiểu vocabulary và cú pháp không?
3. Có thể dự đoán semantics từ đặc tả không?
4. Lỗi có chỉ ra vị trí và nguyên nhân không?
5. Type system có ngăn được lỗi quan trọng không?
6. Runtime có giữ code tách khỏi data không?
7. Rule conflict và no-match đã được định nghĩa chưa?
8. API contract có version và validation không?
9. Plugin có thể nâng cấp độc lập không?
10. Test có bao phủ boundary và security không?
11. Package có thể cài trong môi trường sạch không?
12. Có người chịu trách nhiệm cho thay đổi và release không?

## 23. Câu hỏi phản tư

1. Khái niệm nào trong DSL khó chuyển từ lý thuyết sang implementation nhất?
2. Quyết định thiết kế nào có ảnh hưởng lớn nhất đến khả năng mở rộng?
3. Bạn đã phải thu hẹp scope ở điểm nào?
4. Có rule nào ban đầu tưởng đơn giản nhưng phát sinh conflict không?
5. Loại diagnostic nào giúp người dùng sửa source hiệu quả nhất?
6. Nếu thêm backend thứ hai, phần nào cần thay đổi?
7. Nếu cho người dùng không tin cậy viết rule, threat model thay đổi ra sao?
8. Khi DSL có nhiều consumer, ownership và compatibility cần thay đổi thế nào?

## Kết luận

Các bài tập củng cố giúp người học nhìn DSL như một hệ thống hoàn chỉnh, không chỉ là một cú pháp mới. Một DSL cần xuất phát từ miền và người dùng cụ thể, có vocabulary và model rõ, grammar có thể parse, semantics có thể kiểm chứng, runtime có ranh giới an toàn và kết quả có contract ổn định.

Các phần lexer, parser, type system, compiler/interpreter, API, plugin, security, testing, packaging và governance liên kết với nhau. Một thay đổi ở grammar có thể ảnh hưởng parser và tooling; một thay đổi ở type hoặc payload có thể ảnh hưởng consumer; một plugin mới có thể tạo dependency và rủi ro quyền; một release cần compatibility và migration. Mini-project end-to-end giúp người học thấy những mối liên hệ đó và thực hành lựa chọn trade-off dựa trên yêu cầu thực tế.
