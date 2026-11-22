# Khả năng biểu đạt

## 1. Khả năng biểu đạt trong thiết kế DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) được tạo ra để mô tả một miền vấn đề bằng các khái niệm gần với cách chuyên gia trong miền đó suy nghĩ và làm việc. Khả năng biểu đạt (expressive power) mô tả mức độ ngôn ngữ có thể diễn tả các khái niệm, quy tắc, quan hệ, ràng buộc và hành vi cần thiết trong miền.

Một DSL có khả năng biểu đạt phù hợp cho phép người dùng mô tả công việc trực tiếp, ít phải viết code phụ trợ và ít phải chuyển đổi tư duy sang mô hình kỹ thuật tổng quát. Tuy nhiên, tăng expressive power thường kéo theo grammar phức tạp hơn, nhiều semantics hơn, khó phân tích tĩnh hơn và chi phí bảo trì cao hơn.

Ví dụ một DSL định tuyến có thể cung cấp:

~~~text
route request
    when request.region == "north"
    and request.priority >= HIGH
    to service "priority-queue"
~~~

Đây là cách mô tả gần với ý định nghiệp vụ. Nếu DSL chỉ cho phép khai báo một danh sách route tĩnh, người dùng có thể phải viết thêm code để diễn tả điều kiện. Ngược lại, nếu DSL cho phép mọi construct của một ngôn ngữ lập trình tổng quát, người dùng có thể mất lợi ích của ngôn ngữ miền.

Thiết kế tốt không phải là làm DSL có thể biểu đạt mọi thứ. Mục tiêu là cung cấp đủ sức biểu đạt cho các tác vụ quan trọng trong miền, đồng thời giữ ngôn ngữ dễ học, dễ đọc, dễ phân tích và dễ vận hành.

## 2. Expressiveness và abstraction

Khả năng biểu đạt phụ thuộc vào mức trừu tượng mà DSL cung cấp.

### 2.1. Domain concept

DSL nên có khái niệm phản ánh trực tiếp đối tượng và quy tắc trong miền, ví dụ order, policy, workflow, reservation, approval hoặc transformation.

### 2.2. Domain operation

Một thao tác có thể biểu diễn ý định nghiệp vụ thay vì chi tiết kỹ thuật. Ví dụ authorize_payment có thể che giấu request serialization, token acquisition và HTTP transport.

### 2.3. Constraint

DSL có thể mô tả giới hạn, invariant, precondition và postcondition. Điều này giúp ý định và điều kiện hợp lệ nằm gần nhau.

### 2.4. Relationship

>Ngôn ngữ có thể biểu diễn dependency, ownership, hierarchy, cardinality và temporal relation giữa các thành phần.

### 2.5. Policy

>Policy cho phép khai báo cách hệ thống quyết định trong các tình huống khác nhau, chẳng hạn retry, authorization, routing hoặc retention.

### 2.6. Abstraction level

>Trừu tượng hóa quá thấp buộc người dùng viết nhiều chi tiết hạ tầng. Trừu tượng hóa quá cao có thể che mất những quyết định quan trọng hoặc làm khó debug.

## 3. Các chiều của khả năng biểu đạt

Expressiveness không phải một con số duy nhất. Có thể phân tích theo nhiều chiều.

### 3.1. Syntactic expressiveness

>Grammar có thể biểu diễn bao nhiêu dạng cấu trúc và cách viết. Syntax có thể ngắn gọn, lồng nhau, composable hoặc hỗ trợ abstraction.

### 3.2. Semantic expressiveness

>Ngữ nghĩa cho phép mô tả những loại hành vi, điều kiện và quan hệ nào.

### 3.3. Data expressiveness

>Type system và data model có thể biểu diễn primitive, domain type, union, record, collection, relationship và constraint ra sao.

### 3.4. Control-flow expressiveness

>DSL có thể mô tả sequence, branch, loop, parallelism, event, retry, timeout và compensation ở mức nào.

### 3.5. Composition

>Người dùng có thể kết hợp các construct nhỏ thành policy, workflow hoặc abstraction lớn mà không phải sao chép logic không?

### 3.6. Extensibility

>Ngôn ngữ có thể mở rộng qua function, module, plugin, custom type hoặc extension point không?

### 3.7. Metaprogramming

>Một số DSL cho phép tạo cấu trúc hoặc rule động. Khả năng này mạnh nhưng có thể làm giảm khả năng kiểm tra tĩnh và truy vết.

### 3.8. Temporal expressiveness

>DSL có thể mô tả thời gian, deadline, schedule, event ordering và trạng thái kéo dài hay không?

### 3.9. Uncertainty

>Với miền cần xử lý dữ liệu không chắc chắn, DSL có thể mô tả probability, confidence, range hoặc incomplete information đến mức nào?

## 4. DSL chuyên biệt và ngôn ngữ tổng quát

Một quyết định thiết kế lớn là DSL chỉ hỗ trợ một tập construct chuyên biệt hay tích hợp khả năng của ngôn ngữ tổng quát.

### 4.1. Narrow DSL

>Narrow DSL có grammar nhỏ, tập khái niệm rõ và ít cách biểu đạt cùng một việc. Nó thường dễ học, dễ validate và dễ tạo UI.

### 4.2. Broad DSL

>Broad DSL cung cấp nhiều construct như function, loop, generic, exception, module và abstraction. Người dùng có thể giải quyết nhiều tình huống mà không cần mở rộng language.

### 4.3. General-purpose escape hatch

>DSL có thể cho phép gọi function hoặc viết code trong một vùng embedded language. Cách này tăng linh hoạt nhưng tạo ranh giới mới về type, security, debugging và portability.

### 4.4. Turing completeness

>Một DSL có loop không giới hạn, recursion hoặc khả năng tính toán đủ mạnh có thể trở thành Turing-complete. Điều đó không tự động làm DSL tốt hơn; nó làm tăng phạm vi hành vi và độ khó phân tích.

### 4.5. Deliberate limitation

>Giới hạn một số khả năng có thể là lựa chọn có chủ đích để bảo đảm termination, predictability, security hoặc khả năng sinh code.

### 4.6. Embedded DSL

>Embedded DSL sử dụng cú pháp và type system của host language. Nó dễ tái sử dụng tooling nhưng cú pháp bị giới hạn bởi host language.

### 4.7. External DSL

>External DSL có parser, grammar và tooling riêng. Nó có thể phản ánh domain tốt hơn nhưng cần đầu tư compiler, editor support và versioning.

## 5. Declarative và imperative expressiveness

Hai phong cách này thể hiện mức độ người dùng mô tả mục tiêu hay quy trình thực hiện.

### 5.1. Declarative

>Declarative DSL mô tả trạng thái mong muốn, constraint hoặc policy. Engine quyết định cách thực hiện.

~~~text
access_policy {
    allow role "analyst" to read dataset "sales"
    deny role "guest" to read dataset "sales"
}
~~~

### 5.2. Imperative

>Imperative DSL mô tả các bước thực hiện theo thứ tự.

~~~text
step "load" {
    read dataset "sales"
}
step "filter" {
    keep rows where region == "north"
}
step "publish" {
    write report "north-sales"
}
~~~

### 5.3. Trade-off

>Declarative syntax có thể ngắn và dễ tối ưu nhưng cần engine đủ thông minh. Imperative syntax kiểm soát thứ tự rõ hơn nhưng có thể để người dùng tự xử lý nhiều chi tiết.

### 5.4. Hybrid

>Một DSL có thể khai báo mục tiêu ở mức cao và cho phép custom step ở các điểm cần kiểm soát.

### 5.5. Hidden control flow

>Declarative engine có thể thực hiện retry, parallelism hoặc reordering ẩn bên dưới. Những hành vi ảnh hưởng kết quả cần được công bố và quan sát được.

## 6. Grammar design và mức độ biểu đạt

Grammar quyết định cách người dùng có thể kết hợp các khái niệm.

### 6.1. Orthogonality

>Hai construct orthogonal khi chúng có thể kết hợp theo quy tắc nhất quán mà không tạo nhiều ngoại lệ. Tính orthogonal giúp người dùng suy luận syntax từ những quy tắc đã biết.

### 6.2. Multiple syntax forms

>Cho phép nhiều cách viết cùng một ý định có thể cải thiện sự linh hoạt nhưng làm tăng số trường hợp parser, formatter và documentation phải hỗ trợ.

### 6.3. Nesting

>Block lồng nhau giúp biểu diễn scope và hierarchy. Nesting quá sâu làm source khó đọc và tăng độ phức tạp của parser/diagnostics.

### 6.4. Expression-oriented design

>Cho phép construct trả về value giúp composition tốt hơn. Tuy nhiên, cần xác định type, evaluation order và side effect.

### 6.5. Statement-oriented design

>Statement làm rõ hành động và thứ tự nhưng có thể cần nhiều biến trung gian để kết hợp kết quả.

### 6.6. Syntactic sugar

>Syntactic sugar cung cấp cách viết ngắn cho cấu trúc đã có. Nó cải thiện trải nghiệm nhưng nên có canonical form để formatter và compiler normalize.

### 6.7. Ambiguity budget

>Grammar càng nhiều construct gần giống nhau càng dễ tạo ambiguity. Mỗi cú pháp mới cần được đánh giá về conflict và khả năng giải thích lỗi.

## 7. Type system và expressive power

Type system quyết định loại dữ liệu và quan hệ mà DSL có thể biểu diễn an toàn.

### 7.1. Primitive types

>Boolean, integer, decimal và string đủ cho nhiều cấu hình đơn giản nhưng không diễn tả được hết ý nghĩa miền.

### 7.2. Domain types

>Money, Duration, EmailAddress, CustomerId hoặc Region có thể mang constraint và semantics riêng. Domain type giảm nhầm lẫn giữa các giá trị primitive cùng biểu diễn.

### 7.3. Algebraic data types

>Product type và sum type giúp biểu diễn record, variant và trạng thái rõ ràng.

### 7.4. Optional và nullable

>Type system có thể phân biệt giá trị bắt buộc, optional và nullable. Điều này làm rõ semantics khi field thiếu hoặc null.

### 7.5. Generic types

>Generic cho phép abstraction tái sử dụng trên nhiều type. Tuy nhiên, type inference và diagnostics có thể phức tạp hơn.

### 7.6. Refinement types

>Refinement type có thể biểu diễn giá trị kèm predicate, ví dụ số dương hoặc chuỗi theo pattern. Đây là sức biểu đạt cao nhưng cần solver hoặc validation strategy.

### 7.7. Units of measure

>Type có đơn vị giúp phân biệt milliseconds với seconds, meter với kilometer hoặc amount với currency. Nó giảm lỗi do giá trị số cùng kiểu nhưng khác ý nghĩa.

### 7.8. Subtyping và variance

>Subtyping tăng khả năng tái sử dụng nhưng có thể làm type checking khó dự đoán. Variance cần được định nghĩa nhất quán.

## 8. Expression và function composition

Expression là nền tảng để kết hợp dữ liệu và logic.

### 8.1. First-class expression

>Khi expression có thể được truyền, lưu hoặc trả về như value, DSL hỗ trợ abstraction và composition tốt hơn.

### 8.2. Function

>Function đóng gói logic có tên và có thể tái sử dụng. Signature nên thể hiện input, output, error và side effect.

### 8.3. Higher-order function

>Function nhận hoặc trả function cho phép mô tả transformation, predicate và policy linh hoạt hơn. Nó cũng làm type inference và debugging khó hơn nếu không có tooling tốt.

### 8.4. Pipeline

~~~text
orders
    |> filter(order -> order.is_valid)
    |> map(order -> order.total)
    |> sum()
~~~

Pipeline làm rõ chuỗi biến đổi và hỗ trợ composition. Cần quy định lazy/eager evaluation, error propagation và materialization.

### 8.5. Reusable abstraction

>Người dùng có thể tạo function hoặc module dùng lại một pattern phổ biến thay vì copy source.

### 8.6. Side effect

>Function thuần dễ phân tích và cache. Function có side effect cần annotation hoặc contract rõ để người đọc biết nó có thể ghi dữ liệu, gọi dịch vụ hoặc thay đổi state.

## 9. Control flow và workflow expressiveness

DSL cho workflow cần biểu diễn luồng công việc ở mức đủ cho domain.

### 9.1. Sequence

>Sequence mô tả các bước phụ thuộc theo thứ tự.

### 9.2. Branch

>Branch biểu diễn quyết định theo điều kiện hoặc kết quả.

### 9.3. Loop

>Loop phù hợp xử lý collection hoặc retry. Cần giới hạn hoặc termination rule nếu runtime yêu cầu khả năng kết thúc dự đoán được.

### 9.4. Parallelism

>Parallel construct giúp mô tả các nhánh độc lập. Cần quy định join, cancellation, shared state và failure propagation.

### 9.5. Event-driven flow

>Event-driven DSL có thể mô tả trigger, subscription, correlation và temporal window. Nó phù hợp hệ thống phản ứng nhưng làm thứ tự và state phức tạp hơn.

### 9.6. Compensation

>Workflow phân tán có thể cần compensation khi bước sau thất bại. DSL cần thể hiện quan hệ giữa side effect và hành động bù trừ.

### 9.7. Human task

>Approval hoặc manual review có thể là một node trong workflow. Cần biểu diễn timeout, assignment, escalation và audit.

## 10. Abstraction và reuse

Khả năng định nghĩa abstraction giúp DSL phát triển cùng miền thay vì chỉ là tập cấu hình phẳng.

### 10.1. Named block

>Named block đặt tên cho một nhóm cấu hình hoặc policy để tái sử dụng.

### 10.2. Template

>Template tạo cấu trúc từ parameter. Cần quy định substitution, scope và cách báo lỗi tại vị trí template hay call site.

### 10.3. Module

>Module nhóm declaration và công bố interface. Import/export cần kiểm soát namespace và version.

### 10.4. Inheritance

>Inheritance có thể chia sẻ cấu hình chung nhưng nhiều tầng kế thừa dễ tạo hành vi ẩn và khó biết giá trị cuối đến từ đâu.

### 10.5. Composition

>Composition ghép các policy hoặc component nhỏ. Thường dễ dự đoán hơn inheritance sâu nếu precedence rõ.

### 10.6. Parameterization

>Parameter giúp abstraction linh hoạt. Cần type, default, constraint và error message tốt.

### 10.7. Reuse versus duplication

>Reuse giảm duplication nhưng abstraction quá tổng quát có thể khó hiểu hơn source lặp. Nên trừu tượng hóa pattern ổn định, có ý nghĩa miền.

## 11. Extensibility và plugin model

DSL có thể cần mở rộng khi miền hoặc hệ sinh thái thay đổi.

### 11.1. Built-in feature

>Built-in feature dễ tích hợp với type checker và tooling nhưng làm core language lớn dần.

### 11.2. Extension function

>Extension function thêm hành vi mà không thay grammar. Đây là cách mở rộng tương đối an toàn nếu signature và effect được kiểm soát.

### 11.3. Plugin

>Plugin cho phép bên thứ ba thêm type, function hoặc adapter. Cần versioned API, permission model và lifecycle rõ.

### 11.4. Custom syntax

>Cho phép plugin thêm grammar làm tăng expressive power nhưng có thể tạo conflict giữa plugin và khiến parser không còn xác định.

### 11.5. Capability registry

>Registry mô tả extension nào được bật và version nào hỗ trợ. Compiler có thể kiểm tra capability trước khi resolve symbol.

### 11.6. Portability

>Source dùng plugin riêng có thể không chạy ở môi trường khác. Cần khai báo dependency và capability requirement.

## 12. Expressiveness và static analysis

Khả năng phân tích tĩnh là một lợi ích quan trọng của DSL chuyên biệt.

### 12.1. Name and type analysis

>Compiler có thể kiểm tra symbol, type, required field và function signature trước khi runtime.

### 12.2. Constraint analysis

>DSL có constraint tường minh giúp kiểm tra range, invariant và dependency.

### 12.3. Termination analysis

>Vòng lặp không giới hạn, recursion hoặc dynamic dispatch có thể làm việc chứng minh termination khó hơn.

### 12.4. Effect analysis

>Effect system có thể chỉ ra function nào đọc dữ liệu, ghi state, gọi network hoặc ném exception.

### 12.5. Dependency analysis

>Compiler có thể xây graph của workflow, resource và module để phát hiện cycle hoặc dependency không hợp lệ.

### 12.6. Explainability

>Declarative construct có thể cho phép engine giải thích vì sao một rule được chọn hoặc một policy có hiệu lực.

### 12.7. Dynamic escape hatch

>Code động hoặc plugin tùy ý có thể làm compiler mất khả năng phân tích. Cần phân định rõ vùng tĩnh và vùng dynamic.

## 13. Expressiveness và security

Khả năng mạnh hơn thường đồng nghĩa chương trình có thể thực hiện nhiều loại hành động hơn.

### 13.1. Capability boundary

>DSL nên chỉ cấp capability mà use case cần. Một policy author không nhất thiết cần khả năng đọc file hoặc gọi mạng tùy ý.

### 13.2. Sandboxing

>Expression hoặc plugin do người dùng cung cấp cần chạy trong môi trường giới hạn CPU, memory, time và external access.

### 13.3. Resource control

>Loop, recursion, collection và parallel execution cần budget hoặc limit để tránh resource exhaustion.

### 13.4. Data access

>Type và function cần giới hạn field nhạy cảm, tenant scope và permission.

### 13.5. Determinism

>Deterministic expression dễ audit và replay. Randomness, clock hoặc external lookup cần dependency rõ và có thể kiểm soát.

### 13.6. Auditability

>DSL nên cho phép ghi lại rule, version và decision trace khi hành vi có ảnh hưởng tới nghiệp vụ.

## 14. Expressiveness và performance

Một construct tiện lợi có thể tạo chi phí runtime hoặc compile-time lớn.

### 14.1. Compile-time complexity

>Generic inference, macro expansion, overload resolution và dynamic grammar có thể làm compile chậm hoặc tốn memory.

### 14.2. Runtime overhead

>Reflection, dynamic dispatch, boxing và interpreted expression có thể tăng latency.

### 14.3. Optimization opportunity

>Declarative model giúp compiler reordering, vectorization hoặc query planning khi semantics cho phép.

### 14.4. Predictable cost

>DSL có thể cung cấp cost model, execution budget hoặc limit cho collection và query.

### 14.5. Lazy evaluation

>Lazy evaluation tránh tính dữ liệu không cần nhưng có thể giữ closure và resource lâu hơn.

### 14.6. Materialization

>Chuyển stream thành collection có thể đơn giản hóa thao tác nhưng làm memory tăng theo số phần tử.

### 14.7. Performance transparency

>Người dùng cần biết construct nào có chi phí lớn, đặc biệt khi syntax ngắn gọn che giấu nhiều network call hoặc scan dữ liệu.

## 15. Readability và learnability

Expressiveness chỉ hữu ích nếu người dùng hiểu được chương trình.

### 15.1. Familiar domain language

>Identifier và construct nên dùng thuật ngữ miền đã được hiểu thống nhất.

### 15.2. Consistency

>Cùng một ý nghĩa nên có cùng cách viết và quy tắc ở các phần của DSL.

### 15.3. Local reasoning

>Người đọc nên hiểu được một block mà không cần tra quá nhiều định nghĩa xa hoặc hidden default.

### 15.4. Explicitness

>Giá trị mặc định có thể giảm boilerplate nhưng những default ảnh hưởng security, money hoặc workflow cần hiển thị rõ.

### 15.5. Error messages

>Diagnostic nên chỉ ra construct, expected form, actual value và hướng sửa.

### 15.6. Progressive disclosure

>Người mới có thể dùng subset đơn giản; người có kinh nghiệm khám phá abstraction nâng cao khi cần.

### 15.7. Multiple ways to do the same thing

>Quá nhiều cách biểu đạt cùng một ý định làm source không đồng nhất và khó search. Ưu tiên một canonical style.

## 16. Đánh giá mức biểu đạt theo use case

Không nên đánh giá expressive power chỉ qua số lượng syntax construct.

### 16.1. Coverage of domain tasks

>Liệt kê các tác vụ quan trọng và kiểm tra DSL có mô tả được trực tiếp không.

### 16.2. Boilerplate

>Đo lượng code phụ trợ hoặc custom code cần thiết để hoàn thành use case.

### 16.3. Semantic gap

>Đo khoảng cách giữa thuật ngữ nghiệp vụ và construct kỹ thuật mà người dùng phải viết.

### 16.4. Workaround frequency

>Nhiều workaround lặp lại có thể cho thấy DSL thiếu abstraction hoặc API phù hợp.

### 16.5. Comprehension

>Đánh giá người dùng có thể giải thích ý nghĩa source, dự đoán kết quả và tìm lỗi nhanh hay không.

### 16.6. Static analyzability

>Kiểm tra compiler có thể phát hiện lỗi trước runtime và cung cấp diagnostic có ích đến mức nào.

### 16.7. Extension cost

>Đo chi phí thêm một use case mới: sửa grammar, compiler, runtime, plugin hay chỉ thêm declaration.

### 16.8. Maintenance cost

>Tính đến chi phí documentation, compatibility, migration, testing và support của mỗi construct mới.

## 17. So sánh thiết kế DSL

Một ví dụ routing giúp minh họa trade-off giữa cấu hình đơn giản và logic tổng quát.

### 17.1. Cấu hình tĩnh

~~~text
route "/orders" to service "order-api"
route "/customers" to service "customer-api"
~~~

Cách này dễ đọc và dễ phân tích, nhưng không biểu diễn được routing theo user, tenant hoặc request attribute.

### 17.2. Điều kiện miền

~~~text
route request
    when request.region == "north"
    and request.priority >= HIGH
    to service "priority-queue"
~~~

Cách này tăng khả năng biểu đạt trong phạm vi routing domain và vẫn cho compiler kiểm tra các field, type và operator.

### 17.3. Embedded general-purpose code

~~~text
route request using {
    custom_function(request)
}
~~~

>Cách này linh hoạt hơn nhưng có thể cần quyền thực thi rộng, khó phân tích tĩnh và khó tái lập nếu custom function có side effect.

### 17.4. Lựa chọn

>Chọn mức biểu đạt dựa trên tần suất use case, tính ổn định của domain concept, yêu cầu kiểm tra tĩnh và khả năng vận hành. Không nên thêm general-purpose escape hatch chỉ để xử lý một trường hợp hiếm nếu nó làm tăng đáng kể rủi ro.

## 18. Chi phí của expressive power

Mỗi construct mới tạo ra chi phí xuyên suốt vòng đời.

### 18.1. Grammar and parser

>Thêm production, precedence rule, error recovery và ambiguity case.

### 18.2. Type checker

>Thêm typing rule, inference, constraint và diagnostic.

### 18.3. Runtime

>Thêm evaluator, state, scheduling hoặc effect handling.

### 18.4. Tooling

>Formatter, syntax highlighting, completion, refactoring và language server cần hiểu construct mới.

### 18.5. Documentation

>Người dùng cần ví dụ, reference, migration guide và explanation về semantics.

### 18.6. Compatibility

>Construct cần được hỗ trợ qua version, deprecation và migration trong tương lai.

### 18.7. Test surface

>Mỗi syntax mới làm tăng số tổ hợp cần kiểm tra với type, scope, error và runtime.

### 18.8. Cognitive load

>Người dùng phải học và ghi nhớ construct. Một ngôn ngữ có quá nhiều khả năng hiếm dùng có thể khó tiếp cận.

## 19. Chiến lược kiểm soát expressive power

Nhóm thiết kế có thể dùng một số nguyên tắc để giữ DSL tập trung.

### 19.1. Domain-first

>Bắt đầu từ tác vụ và thuật ngữ miền, không bắt đầu bằng việc sao chép feature của một general-purpose language.

### 19.2. Small core

>Giữ core language nhỏ, nhất quán và có semantics ổn định.

### 19.3. Composition over special cases

>Ưu tiên construct nhỏ có thể kết hợp thay vì thêm một syntax riêng cho từng use case.

### 19.4. Explicit extension points

>Cho phép mở rộng qua function, adapter hoặc plugin có contract rõ.

### 19.5. Safe defaults

>Giới hạn resource, side effect và permission theo mặc định; người dùng phải khai báo rõ khi cần quyền mạnh hơn.

### 19.6. Canonical form

>Formatter hoặc compiler normalize các cách viết tương đương về một canonical representation.

### 19.7. Measure before expanding

>Thu thập use case, workaround và feedback trước khi thêm construct mới.

### 19.8. Deprecate carefully

>Khi loại construct, cung cấp migration path và thời gian hỗ trợ hợp lý.

## 20. Những sai lầm thường gặp

### 20.1. Đồng nhất expressive power với số lượng keyword

>Nhiều keyword không nhất thiết giúp mô tả miền tốt hơn. Composition và type model có thể tạo sức biểu đạt lớn hơn với grammar nhỏ.

### 20.2. Biến DSL thành general-purpose language

>Thêm loop, function, class, reflection và arbitrary code có thể làm mất lợi ích domain-specific nếu không có mục tiêu rõ.

### 20.3. Syntax ngắn nhưng semantics ẩn

>Viết ít ký tự không đồng nghĩa dễ hiểu. Hidden default và implicit side effect làm tăng chi phí debug.

### 20.4. Thiếu type hoặc domain concept

>Dùng primitive cho mọi thứ khiến người dùng phải tự nhớ đơn vị, range và meaning.

### 20.5. Abstraction quá tổng quát

>Template hoặc inheritance sâu có thể che giấu giá trị cuối và làm khó truy vết.

### 20.6. Extension không có sandbox

>Plugin hoặc embedded code tùy ý có thể phá resource boundary và security model.

### 20.7. Không tính chi phí tooling

>Syntax mới nhưng không có formatter, completion và diagnostic tốt sẽ làm trải nghiệm kém.

### 20.8. Không có canonical style

>Nhiều cách viết tương đương làm source khó review, diff và search.

### 20.9. Không đo use case thực tế

>Thiết kế dựa trên giả định có thể tạo construct ít dùng nhưng đắt để duy trì.

## 21. Quy trình đánh giá một đề xuất mở rộng DSL

1. **Mô tả use case.** Xác định ai cần khả năng mới và vấn đề hiện tại.
2. **Đo workaround.** Thu thập source hoặc custom code đang được dùng để giải quyết vấn đề.
3. **Xác định domain concept.** Tìm abstraction phản ánh ý nghĩa miền thay vì chi tiết implementation.
4. **So sánh phương án.** Syntax mới, composition từ construct hiện có, library function hoặc plugin.
5. **Đánh giá expressive gain.** Use case nào được giải quyết và boilerplate giảm bao nhiêu?
6. **Đánh giá complexity cost.** Grammar, type system, runtime, tooling, docs và compatibility cần thay đổi gì?
7. **Kiểm tra static analysis.** Compiler còn có thể kiểm tra type, constraint, dependency và termination đến đâu?
8. **Đánh giá security.** Quyền và resource mới được cấp có làm tăng attack surface không?
9. **Thiết kế canonical form.** Xác định formatter và normalization.
10. **Thử nghiệm với người dùng miền.** Đánh giá readability, learnability và khả năng giải thích.
11. **Định nghĩa version policy.** Xác định feature gate, stability và migration nếu cần.
12. **Quyết định.** Chấp nhận, thử nghiệm, trì hoãn hoặc từ chối dựa trên giá trị và chi phí vòng đời.

## 22. Câu hỏi tự kiểm tra

1. Khả năng biểu đạt của DSL là gì?
2. Phân biệt syntactic, semantic, data, control-flow và temporal expressiveness.
3. Vì sao expressive power không phải mục tiêu tối đa hóa vô điều kiện?
4. DSL hẹp, DSL rộng và general-purpose escape hatch có trade-off gì?
5. Turing completeness ảnh hưởng termination, security và static analysis ra sao?
6. Declarative và imperative expressiveness khác nhau thế nào?
7. Orthogonality và composability giúp ngôn ngữ dễ học ra sao?
8. Type system có thể tăng expressive power bằng domain type, union, generic và refinement như thế nào?
9. Function composition và pipeline hỗ trợ reuse ra sao?
10. Control flow, parallelism và event construct cần semantics nào?
11. Inheritance, template và composition có ưu nhược điểm gì?
12. Plugin và custom syntax ảnh hưởng portability và parser stability thế nào?
13. Expressive power có thể làm giảm khả năng phân tích tĩnh ra sao?
14. Những rủi ro security nào xuất hiện khi DSL cho phép arbitrary code?
15. Expressiveness ảnh hưởng compile-time và runtime performance thế nào?
16. Làm thế nào đánh giá readability, learnability và semantic gap?
17. Những chi phí vòng đời nào phát sinh khi thêm một construct?
18. Vì sao nên có small core và canonical form?
19. Hãy so sánh ba cách biểu diễn một policy routing: cấu hình tĩnh, điều kiện miền và embedded code.
20. Hãy xây dựng tiêu chí quyết định có nên thêm một construct mới vào DSL đang được nhiều team sử dụng.
