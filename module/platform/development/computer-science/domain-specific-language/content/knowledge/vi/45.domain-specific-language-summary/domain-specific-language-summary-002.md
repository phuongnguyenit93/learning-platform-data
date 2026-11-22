# Quy trình thiết kế hoàn chỉnh

Thiết kế một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) là một công việc xuyên suốt từ nghiên cứu miền nghiệp vụ đến triển khai compiler, runtime, công cụ phát triển và vận hành lâu dài. Một DSL thành công không chỉ có cú pháp dễ đọc. Nó phải biểu diễn đúng khái niệm của miền, có semantics nhất quán, phát hiện lỗi sớm, thực thi an toàn, tích hợp được với hệ thống hiện tại và có thể tiến hóa khi yêu cầu thay đổi.

**Quy trình thiết kế hoàn chỉnh** là phương pháp tổ chức các quyết định và hoạt động cần thiết để đưa DSL từ ý tưởng thành một sản phẩm có thể sử dụng và bảo trì. Quy trình này kết hợp phân tích domain, xác định phạm vi, thiết kế vocabulary, syntax, type system, semantics, grammar, AST, compiler hoặc interpreter, runtime, security, tooling, testing, documentation, release và governance.

Không có một quy trình duy nhất phù hợp mọi DSL. Một DSL nhỏ để tính biểu thức có thể chỉ cần parser, evaluator và một API hẹp. Một DSL mô tả workflow dài hạn cần state persistence, event handling, retry, observability và migration. Một DSL query cần logical plan, optimizer, backend và semantics tương thích với nguồn dữ liệu. Quy trình phải được điều chỉnh theo mục tiêu, rủi ro và độ phức tạp của miền.

Bài học này trình bày toàn bộ vòng đời thiết kế DSL, các quyết định ở từng giai đoạn, cách tạo prototype, lựa chọn kiến trúc, thiết kế ngôn ngữ, triển khai toolchain, bảo mật, kiểm thử, phát hành và quản trị. Một ví dụ xuyên suốt về DSL xử lý đơn hàng minh họa cách kết nối các bước thành một kế hoạch thực tế.

## 1. Xác định vấn đề và mục tiêu

Điểm khởi đầu không phải là chọn parser generator hoặc nghĩ ra cú pháp. Trước tiên cần xác định vấn đề nào cần được giải quyết và vì sao một DSL có ích.

### 1.1. Mô tả vấn đề hiện tại

Tìm hiểu cách người dùng đang giải quyết công việc:
- Viết code trong ngôn ngữ tổng quát.
- Dùng spreadsheet hoặc form.
- Chỉnh sửa file cấu hình.
- Viết query hoặc script.
- Nhập rule vào một công cụ riêng.
- Thực hiện thao tác thủ công.
- Phối hợp qua nhiều hệ thống.

Ghi lại điểm đau cụ thể như lỗi lặp lại, khó kiểm tra, thời gian thay đổi lâu, phụ thuộc đội kỹ thuật hoặc khó audit.

### 1.2. Xác định người dùng

Người viết DSL có thể là:
- Developer.
- Analyst.
- Domain expert.
- Operator.
- Administrator.
- Integration engineer.
- End user có quyền cấu hình.

Mỗi nhóm có kỹ năng, từ vựng và nhu cầu khác nhau. Cú pháp phù hợp với developer có thể không phù hợp với chuyên viên nghiệp vụ.

### 1.3. Xác định mục tiêu đo được

Ví dụ:
- Giảm thời gian tạo một rule.
- Cho phép domain expert tự sửa policy.
- Phát hiện type error trước khi deploy.
- Tái sử dụng workflow giữa nhiều dự án.
- Hạn chế quyền thực thi.
- Rút ngắn thời gian kiểm tra thay đổi.
- Tăng khả năng audit.

Mục tiêu nên có chỉ số hoặc tiêu chí chấp nhận để đánh giá DSL có tạo ra giá trị hay không.

### 1.4. Xác định khi nào không cần DSL

Nếu vấn đề chỉ có vài cấu hình đơn giản, một schema configuration hoặc API có thể đủ. DSL có chi phí thiết kế, parser, diagnostics, tooling và documentation. Chỉ nên xây khi khả năng biểu đạt và kiểm soát đem lại lợi ích lớn hơn chi phí.

### 1.5. Viết problem statement

Một problem statement tốt nêu:
- Ai gặp vấn đề.
- Công việc nào cần thực hiện.
- Khó khăn hiện tại.
- Kết quả mong muốn.
- Giới hạn và giả định.
- Cách đo thành công.

## 2. Khảo sát domain và chuyên gia nghiệp vụ

DSL phải phản ánh đúng miền mà nó phục vụ. Nếu vocabulary sai hoặc mô hình hóa không đúng, cú pháp đẹp cũng không cứu được thiết kế.

### 2.1. Thu thập thuật ngữ

Phỏng vấn domain expert, đọc tài liệu nghiệp vụ, quan sát quy trình và thu thập ví dụ thực tế. Tạo glossary cho entity, event, state, rule, action và thuật ngữ có ý nghĩa đặc biệt.

### 2.2. Phân biệt từ đồng nghĩa

Một nhóm có thể dùng nhiều từ cho cùng một khái niệm. Cần thống nhất tên chính thức hoặc ghi rõ alias. Tránh để một từ có nhiều nghĩa không liên quan trong cùng phạm vi.

### 2.3. Xác định entity và value object

Entity có identity và vòng đời. Value object biểu diễn giá trị theo type và thường không có identity riêng.

Ví dụ trong miền đơn hàng:
- Order là entity.
- OrderItem có thể là entity con hoặc value object tùy lifecycle.
- Money là value object.
- Currency là type hoặc enum.
- Address có thể là value object.

### 2.4. Xác định event và command

Command yêu cầu hệ thống thực hiện hành động. Event biểu diễn việc đã xảy ra. Phân biệt hai loại này giúp thiết kế workflow và integration rõ ràng.

### 2.5. Xác định state và invariant

State mô tả giai đoạn hiện tại. Invariant là điều kiện phải luôn đúng. Ví dụ, đơn hàng ở PAID phải có payment reference hợp lệ.

### 2.6. Domain workshop

Dùng ví dụ cụ thể để chuyên gia và developer cùng diễn giải. Hỏi điều gì xảy ra khi dữ liệu thiếu, actor không đủ quyền, event đến trễ hoặc action thất bại.

### 2.7. Domain model và ubiquitous language

Tạo mô hình chung và dùng cùng vocabulary trong DSL, documentation, code và thảo luận. Khi domain expert nói một thuật ngữ, mọi thành phần nên hiểu cùng một ý nghĩa.

## 3. Xác định phạm vi và ranh giới DSL

Không nên cố gắng biểu diễn toàn bộ domain trong phiên bản đầu.

### 3.1. Chọn use case trọng tâm

Chọn một nhóm công việc có tần suất cao, quy tắc tương đối ổn định và giá trị rõ. Ví dụ:
- Tính giá.
- Validation.
- Query báo cáo.
- Workflow phê duyệt.
- Mapping dữ liệu.
- Policy truy cập.

### 3.2. Xác định non-goals

Ghi rõ những việc DSL không giải quyết. Ví dụ, DSL rule không phải ngôn ngữ general-purpose, không cho phép truy cập file tùy ý và không thay thế hệ thống identity.

### 3.3. Phân chia capability

Có thể xác định:
- Core language.
- Domain library.
- Host API.
- Runtime service.
- IDE tooling.
- Deployment integration.

Phân chia này giúp không nhồi mọi khả năng vào grammar.

### 3.4. Xác định trust boundary

Ai có thể viết source? Ai được chạy? Dữ liệu nào được truy cập? Có side effect không? Mỗi nhóm người dùng có quyền gì? Các câu hỏi này ảnh hưởng trực tiếp đến architecture và sandbox.

### 3.5. Xác định target environment

DSL chạy local, server, browser, embedded device, cloud hoặc nhiều môi trường? Target ảnh hưởng runtime, resource model, security và portability.

### 3.6. Xác định lifecycle

Chương trình được viết một lần hay thay đổi thường xuyên? Có chạy hàng năm không? Có cần giữ workflow instance qua nhiều lần release không? Lifecycle dài hạn đòi hỏi versioning và migration.

## 4. Xây dựng yêu cầu và use case

Yêu cầu nên cụ thể và có thể chuyển thành test.

### 4.1. Functional requirement

Mô tả DSL phải biểu đạt được điều gì:
- Khai báo type.
- Viết expression.
- Tạo rule.
- Query dữ liệu.
- Khai báo workflow.
- Gọi action.
- Tạo artifact.

### 4.2. Non-functional requirement

Bao gồm:
- Performance.
- Reliability.
- Security.
- Scalability.
- Portability.
- Usability.
- Observability.
- Maintainability.

### 4.3. Use case specification

Mỗi use case nên có actor, precondition, input, main flow, alternate flow, output và error behavior.

### 4.4. Acceptance criteria

Ví dụ: một rule tính discount phải cho kết quả xác định với các boundary value, không truy cập dữ liệu ngoài scope và có diagnostic khi input sai.

### 4.5. Prioritization

Có thể chia:
- Must have.
- Should have.
- Could have.
- Not in initial release.

Ưu tiên semantics cốt lõi và một vertical slice chạy được trước khi mở rộng cú pháp.

## 5. Chọn loại DSL và execution model

Có nhiều cách triển khai DSL. Lựa chọn cần dựa trên use case.

### 5.1. External DSL

External DSL có grammar và source format riêng. Nó phù hợp khi cần cú pháp độc lập, parser riêng và tooling chuyên biệt.

### 5.2. Internal DSL

Internal DSL được xây trên một host language. Nó tận dụng type system, compiler và IDE của host nhưng cú pháp bị giới hạn bởi host language.

### 5.3. Declarative DSL

Declarative DSL mô tả kết quả hoặc ràng buộc mong muốn. Engine quyết định cách thực thi.

### 5.4. Imperative DSL

Imperative DSL mô tả chuỗi thao tác hoặc control flow. Nó phù hợp với quy trình có thứ tự và state mutation.

### 5.5. Hybrid DSL

Một DSL có thể kết hợp khai báo domain model, rule declarative và workflow imperative. Cần giữ ranh giới rõ để người dùng hiểu semantics.

### 5.6. Interpreter

Interpreter trực tiếp đánh giá AST hoặc IR. Nó dễ bắt đầu và linh hoạt, nhưng có thể chịu dispatch overhead.

### 5.7. Compiler

Compiler chuyển DSL sang bytecode, source code hoặc artifact target. Nó có thể tối ưu và phát hiện lỗi trước runtime, nhưng có chi phí build và compatibility.

### 5.8. Hybrid execution

Có thể interpret trong development, compile khi deploy hoặc compile một số phần và interpret phần còn lại.

## 6. Thiết kế vocabulary và conceptual model

Trước khi viết grammar, xác định các khái niệm người dùng sẽ nhìn thấy.

### 6.1. Chọn từ khóa

Từ khóa nên phản ánh ngôn ngữ của domain. Dùng từ phổ biến, nhất quán và ít gây nhầm với host language.

### 6.2. Naming convention

Định nghĩa quy ước đặt tên cho:
- Type.
- Field.
- Function.
- Predicate.
- Rule.
- Event.
- State.
- Module.
- Constant.

### 6.3. Cấp độ trừu tượng

Xác định người dùng làm việc ở cấp domain operation hay primitive. Một DSL pricing nên cho phép viết calculateDiscount thay vì bắt người dùng quản lý memory hoặc database cursor.

### 6.4. Default behavior

Mọi default cần có semantics rõ. Ví dụ, field optional có giá trị null hay được gán default? Query không có order by có đảm bảo ordering không?

### 6.5. Error vocabulary

Thống nhất cách diễn đạt parse error, type error, validation issue, permission denial và runtime failure.

### 6.6. Concept map

Có thể vẽ quan hệ:

~~~text
Domain Type
    |
    v
Expression
    |
    v
Function / Predicate
    |
    v
Rule / Policy / Query
    |
    v
Workflow / Application
~~~

Sơ đồ giúp xác định construct nào là nền tảng và construct nào là abstraction cấp cao.

## 7. Thiết kế type system và data model

Type system giúp chương trình diễn đạt dữ liệu rõ và phát hiện lỗi sớm.

### 7.1. Primitive type

Xác định Integer, Decimal, Boolean, String, Date, Instant, Duration và các type cần thiết.

### 7.2. Domain type

Tạo type riêng như OrderId, CustomerId, Money, EmailAddress và CurrencyCode. Type riêng giúp tránh truyền nhầm giá trị cùng representation.

### 7.3. Record và entity

Khai báo field, nullability, constraint, identity và relationship.

### 7.4. Enum và union

Enum biểu diễn tập giá trị hữu hạn. Union biểu diễn một trong nhiều dạng. Cần policy khi gặp giá trị chưa biết.

### 7.5. Generic

Generic cho phép function và collection hoạt động với nhiều type mà không mất type safety.

### 7.6. Optional và Result

Optional thể hiện giá trị có thể vắng mặt. Result thể hiện success hoặc failure. Chúng giúp composition và error handling rõ ràng.

### 7.7. Numeric semantics

Định nghĩa precision, scale, overflow, rounding và conversion. Với tiền tệ, ưu tiên Decimal hoặc Money type có semantics rõ.

### 7.8. Type inference

Quyết định phần nào được suy luận và phần nào cần annotation. Inference quá mạnh có thể làm diagnostics khó hiểu hoặc compile time tăng.

### 7.9. Null semantics

Định nghĩa null trong expression, comparison, collection, query và serialization. Tránh để semantics khác nhau giữa compiler và database.

## 8. Thiết kế syntax và grammar

Syntax là bề mặt người dùng viết. Grammar mô tả cấu trúc hợp lệ.

### 8.1. Chọn notation

Có thể dùng:
- Block syntax.
- Expression syntax.
- Indentation-based syntax.
- JSON hoặc YAML-like syntax.
- Fluent API.
- Table-oriented syntax.

Chọn theo domain, readability và tooling.

### 8.2. Operator precedence

Định nghĩa precedence và associativity. Ví dụ phép nhân có precedence cao hơn cộng.

### 8.3. Statement và expression

Statement thực hiện hành động. Expression tạo giá trị. Phân biệt rõ giúp type checker và control flow đơn giản hơn.

### 8.4. Grammar modularity

Tách grammar theo declaration, expression, query, workflow và policy khi phù hợp. Tránh grammar khổng lồ khó bảo trì.

### 8.5. Error recovery

Parser nên tiếp tục sau một lỗi để phát hiện thêm diagnostic, nhưng không tạo AST giả có thể gây lỗi dây chuyền khó hiểu.

### 8.6. Syntax evolution

Định nghĩa cách thêm keyword, operator và syntax version. Tránh thay đổi meaning của cú pháp cũ mà không có versioning.

### 8.7. Prototype syntax

Thử syntax với người dùng trên các ví dụ thật. Đo khả năng đọc, khả năng viết và lỗi thường gặp trước khi đóng băng grammar.

## 9. Xây parser, AST và source model

Parser chuyển source thành cấu trúc có thể xử lý.

### 9.1. Lexing

Lexer tạo token từ source. Cần xử lý Unicode, comment, string escape, number literal và source location.

### 9.2. Parsing

Parser kiểm tra grammar và tạo parse tree hoặc AST. Chọn parser generator hoặc parser viết tay theo grammar và yêu cầu recovery.

### 9.3. AST

AST nên biểu diễn khái niệm ngôn ngữ, không sao chép nguyên cấu trúc parser framework nếu điều đó tạo coupling không cần thiết.

### 9.4. Source range

Mỗi node nên giữ source range để diagnostics, navigation, refactoring và debugger có thể trỏ về đúng vị trí.

### 9.5. Error node

AST có thể chứa node lỗi hoặc missing node để tiếp tục phân tích mà không làm sập toàn pipeline.

### 9.6. AST transformation

Optimizer hoặc macro expansion có thể biến đổi AST. Cần giữ source mapping và thông tin origin.

### 9.7. Serialization

Nếu AST hoặc IR được lưu cache, định dạng serialization cần version và validation.

## 10. Semantic analysis và name resolution

Parse thành công không có nghĩa chương trình hợp lệ.

### 10.1. Symbol table

Tạo symbol table cho type, variable, function, module, rule và event.

### 10.2. Scope

Định nghĩa lexical scope, module scope, function scope và workflow context. Quy tắc shadowing cần rõ.

### 10.3. Name resolution

Resolve identifier đến declaration phù hợp. Diagnostic cần chỉ ra tên chưa resolve hoặc tên bị ambiguous.

### 10.4. Type checking

Kiểm tra argument, return type, operator, field access, generic constraint và conversion.

### 10.5. Semantic validation

Kiểm tra quy tắc không biểu diễn hết trong grammar hoặc type system, ví dụ state target tồn tại, transition không ambiguous và capability được khai báo.

### 10.6. Dependency analysis

Xây graph giữa module, function, type, rule và workflow. Phát hiện cycle hoặc dependency không hợp lệ.

### 10.7. Diagnostic model

Diagnostic có code, severity, message, source range, related location và quick fix nếu có.

## 11. Định nghĩa semantics của ngôn ngữ

Semantics là ý nghĩa và hành vi của chương trình.

### 11.1. Evaluation order

Quy định thứ tự đánh giá expression, function argument, branch và collection operation.

### 11.2. Short-circuit

Định nghĩa and/or có short-circuit hay luôn đánh giá cả hai phía. Điều này quan trọng nếu expression có lỗi hoặc effect.

### 11.3. Function behavior

Xác định pure function, async function, exception và recursion.

### 11.4. Rule behavior

Định nghĩa first-match, priority, collect-all hoặc ambiguity error.

### 11.5. Query semantics

Định nghĩa null, ordering, grouping, collation, pagination và transaction snapshot.

### 11.6. Workflow semantics

Định nghĩa event dispatch, guard, transition, entry/exit action, timeout, cancellation và final state.

### 11.7. Error semantics

Phân biệt compile error, validation error, business rejection và technical failure. Xác định lỗi nào được recover.

### 11.8. Determinism

Định nghĩa nguồn nondeterminism như time, random, external data và concurrent execution.

### 11.9. Semantic specification

Viết tài liệu và test reference cho từng construct. Tránh để behavior chỉ tồn tại trong implementation.

## 12. Thiết kế composition và abstraction

Các construct cần kết hợp thành chương trình lớn.

### 12.1. Expression và function

Tạo expression từ literal, operator và function. Function có input/output type rõ.

### 12.2. Rule và policy

Rule nhỏ có thể được kết hợp thành policy với precedence và default behavior.

### 12.3. Query và pipeline

Source, filter, join, group, aggregate và projection tạo thành query plan.

### 12.4. Workflow và sub-workflow

Step và state có thể được kết hợp tuần tự, song song hoặc có điều kiện. Parent cần nhận completion và failure của child.

### 12.5. Module

Module quản lý namespace, public API, dependency và version.

### 12.6. Reuse

Tạo library theo domain nhưng tránh abstraction tổng quát không cần thiết. Component cần có contract và ví dụ.

### 12.7. Effect boundary

Tách pure computation khỏi action có side effect. Action cần capability, timeout, retry và idempotency.

## 13. Thiết kế compiler hoặc interpreter architecture

Kiến trúc thực thi cần hỗ trợ semantics đã định nghĩa.

### 13.1. Compiler pipeline

Một pipeline thường gồm:
1. Load source.
2. Parse.
3. Semantic analysis.
4. Validation.
5. Lowering sang IR.
6. Optimization.
7. Code generation.
8. Packaging.

### 13.2. Interpreter

Interpreter đánh giá AST hoặc IR. Nó phù hợp prototype hoặc runtime cần linh hoạt.

### 13.3. Intermediate representation

IR giúp tách front end khỏi backend, hỗ trợ optimization và nhiều target.

### 13.4. Code generation

Target có thể là bytecode, host code, SQL, JSON Schema hoặc workflow definition. Mỗi target cần mapping semantics và diagnostic khi feature không hỗ trợ.

### 13.5. Incremental compilation

Cache kết quả theo source và dependency version. Invalidation phải chính xác khi declaration hoặc dependency thay đổi.

### 13.6. Reproducibility

Cùng source, compiler, dependency và configuration nên tạo artifact tương đương theo contract.

### 13.7. Compiler API

Expose API ổn định để CLI, IDE, build plugin và runtime dùng chung compiler core.

## 14. Runtime và host integration

Runtime cung cấp context và khả năng thực thi.

### 14.1. Execution context

Context có thể chứa tenant, actor, locale, clock, correlation ID và resource budget. Giá trị phải đến từ nguồn đáng tin cậy.

### 14.2. Host API

Expose API theo domain, không đưa toàn bộ service container vào DSL.

### 14.3. Capability

Cấp quyền cụ thể theo execution. Host kiểm tra permission tại thời điểm thực hiện action.

### 14.4. Async và event

Định nghĩa await, event subscription, cancellation, timeout và correlation.

### 14.5. Persistence

Workflow dài hạn cần lưu state, context, timer và retry metadata.

### 14.6. Error mapping

Host exception được chuyển thành error model an toàn, có code và context.

### 14.7. Runtime versioning

Artifact cần ghi runtime compatibility. Runtime cần biết cách load artifact và context version cũ.

## 15. Security và sandbox

Bảo mật phải được thiết kế ngay từ đầu nếu DSL có thể chạy code hoặc rule do người dùng cung cấp.

### 15.1. Threat model

Xác định tài sản, actor, input không tin cậy, đường tấn công và hậu quả.

### 15.2. Least privilege

Mỗi execution chỉ nhận capability cần thiết.

### 15.3. Sandbox

Giới hạn filesystem, network, process, CPU, memory, recursion và output size.

### 15.4. Tenant isolation

Tenant context do host cấp. Data service áp dụng tenant scope và authorization.

### 15.5. Secret handling

Không expose credential vào DSL source hoặc context nếu không cần. Dùng secret reference và host adapter.

### 15.6. Input và output validation

Kiểm tra schema, size, range, encoding và invariant ở boundary.

### 15.7. Audit

Ghi actor, policy version, capability operation và outcome cho thao tác nhạy cảm.

### 15.8. Supply chain

Pin dependency, scan vulnerability, kiểm tra license và provenance.

## 16. Error handling, observability và vận hành

Một DSL có thể compile đúng nhưng vẫn cần công cụ để điều tra khi runtime lỗi.

### 16.1. Diagnostic

Diagnostic phải có code ổn định, source location và hướng xử lý.

### 16.2. Structured logging

Log có run ID, stage, component, severity và correlation context.

### 16.3. Metrics

Đo compile duration, runtime latency, throughput, memory, retry, error rate và queue depth.

### 16.4. Distributed tracing

Trace liên kết compiler, host service, database và workflow engine.

### 16.5. State dashboard

Workflow cần hiển thị state, duration, pending event và failure.

### 16.6. Alert

Alert theo triệu chứng và tác động, có owner và runbook.

### 16.7. Incident recovery

Định nghĩa retry, replay, compensation, manual intervention và recovery.

## 17. Tooling và trải nghiệm người dùng

Tooling quyết định DSL có thực sự dễ sử dụng hay không.

### 17.1. CLI

CLI hỗ trợ init, parse, validate, format, compile, test, package và deploy.

### 17.2. IDE integration

Syntax highlight, completion, navigation, diagnostics, refactoring và debugger.

### 17.3. Language Server

Language server giúp dùng language intelligence trên nhiều editor.

### 17.4. Formatter

Formatter thống nhất style để giảm tranh luận và diff noise.

### 17.5. Linter

Linter cảnh báo pattern khó đọc, deprecated feature và cấu hình rủi ro.

### 17.6. Debugger

Debugger hỗ trợ breakpoint, step, inspect value, state và trace.

### 17.7. Documentation tooling

Generate reference từ schema hoặc API metadata khi có thể. Ví dụ cần chạy lại và ghi version.

### 17.8. Migration tooling

Cung cấp command để validate schema, plan migration, dry-run và report kết quả.

## 18. Testing strategy

Test cần bao phủ cả ngôn ngữ, compiler, runtime và tích hợp.

### 18.1. Lexer và parser test

Test token, grammar, precedence, malformed input và error recovery.

### 18.2. Golden test

Lưu expected AST, IR, generated code hoặc diagnostics.

### 18.3. Type checker test

Test type inference, overload, generic, nullability và invalid combination.

### 18.4. Semantic test

Test rule precedence, query semantics, workflow transition và error behavior.

### 18.5. Property-based test

Sinh input để kiểm tra invariant và tính chất tổng quát.

### 18.6. Integration test

Test database, host API, message broker, identity và sandbox.

### 18.7. Conformance test

Nếu có nhiều backend hoặc runtime, chạy cùng suite để xác minh semantics.

### 18.8. Performance test

Benchmark parse, compile, incremental compile, runtime, query và memory.

### 18.9. Security test

Test capability denial, path traversal, SSRF, resource exhaustion, tenant isolation và plugin boundary.

### 18.10. Recovery test

Test crash, restart, retry, duplicate event, timeout và migration instance.

## 19. Documentation và developer experience

Documentation là một phần của thiết kế ngôn ngữ.

### 19.1. Language reference

Mô tả grammar, type, operator, scope, evaluation order và error semantics.

### 19.2. Getting started

Hướng dẫn cài toolchain, tạo project, chạy ví dụ và debug lỗi đầu tiên.

### 19.3. Domain guide

Giải thích vocabulary, model và cách ánh xạ yêu cầu nghiệp vụ sang DSL.

### 19.4. Example library

Có ví dụ nhỏ theo feature và ví dụ hoàn chỉnh theo scenario. Mỗi ví dụ có input và expected output.

### 19.5. API reference

Tài liệu host function, capability, extension và version compatibility.

### 19.6. Troubleshooting

Giải thích diagnostic code, common runtime failure và cách thu thập log.

### 19.7. Migration guide

Mô tả breaking change, mapping schema, deprecated feature và upgrade path.

### 19.8. Documentation quality

Ví dụ cần được chạy trong CI nếu có thể. Documentation lỗi hoặc syntax cũ có thể làm người dùng mất niềm tin.

## 20. Versioning và compatibility

DSL cần tiến hóa mà không phá vỡ người dùng bất ngờ.

### 20.1. Language version

Mỗi artifact hoặc project có thể khai báo language version.

### 20.2. Compiler version

Compiler version riêng với language version. Nhiều compiler có thể implement cùng language specification.

### 20.3. Runtime compatibility

Artifact cần khai báo runtime requirement hoặc target ABI.

### 20.4. Deprecation

Đánh dấu feature deprecated, đưa warning, thời gian chuyển đổi và migration tool.

### 20.5. Breaking change

Breaking change cần major version hoặc language version mới, compatibility note và test.

### 20.6. Schema migration

Thay đổi record, event, API và workflow context cần migration path.

### 20.7. Long-running instance

Instance đang chạy có thể pin definition cũ hoặc được migrate ở checkpoint an toàn.

### 20.8. Reproducible artifact

Lưu dependency version, compiler version, schema version và configuration để tái tạo.

## 21. Release và deployment

Release cần đưa đúng artifact vào môi trường đích và giữ khả năng truy nguyên.

### 21.1. Artifact package

Package chứa compiled output, manifest, dependency metadata, source map và signature nếu cần.

### 21.2. Validation trước release

Chạy parser, type checker, validator, test và policy check.

### 21.3. Environment configuration

Tách source DSL khỏi secret và environment-specific configuration.

### 21.4. Staged rollout

Triển khai dev, staging, canary rồi production theo policy.

### 21.5. Rollback

Xác định artifact trước đó, database compatibility và state recovery. Rollback application không tự đảo ngược data migration.

### 21.6. Provenance

Ghi source revision, build identity, compiler, dependency và artifact checksum.

### 21.7. Release notes

Ghi feature mới, breaking change, deprecation, security fix và migration instruction.

## 22. Governance và quản trị DSL

Khi nhiều nhóm dùng DSL, cần quy trình quản lý thay đổi.

### 22.1. Ownership

Xác định owner cho language core, domain library, runtime, toolchain và documentation.

### 22.2. Proposal process

Thay đổi syntax hoặc semantics cần proposal với motivation, alternatives, compatibility và migration impact.

### 22.3. Review

Domain expert review vocabulary và business meaning. Compiler engineer review grammar và semantics. Security và operations review capability và runtime impact.

### 22.4. Extension policy

Quy định ai được thêm function, plugin, type và target backend.

### 22.5. Compatibility policy

Định nghĩa thời gian hỗ trợ version, deprecation window và migration support.

### 22.6. Release cadence

Chọn release schedule và policy hotfix. Tránh thay đổi semantics ngoài quy trình versioning.

### 22.7. Telemetry và feedback

Thu thập feature usage, diagnostic frequency và performance data theo chính sách quyền riêng tư để ưu tiên cải tiến.

## 23. Ví dụ xuyên suốt: thiết kế DSL xử lý đơn hàng

Giả sử tổ chức muốn domain expert khai báo quy tắc và workflow xử lý đơn hàng mà không phải sửa application code mỗi lần chính sách thay đổi.

### 23.1. Problem statement

Hiện tại rule giá, kiểm tra tồn kho và phê duyệt nằm trong nhiều service. Thay đổi chính sách cần release code và khó audit. Mục tiêu là đưa rule và workflow vào một DSL có type safety, versioning và kiểm soát quyền.

### 23.2. Domain vocabulary

Các khái niệm chính:
- Order.
- Customer.
- OrderItem.
- Money.
- Inventory.
- Payment.
- Shipment.
- Approval.
- OrderSubmitted.
- PaymentAccepted.

### 23.3. Data model

~~~text
record Order {
  id: OrderId
  customerId: CustomerId
  items: List<OrderItem>
  total: Money
  status: OrderStatus
}

record OrderItem {
  sku: Sku
  quantity: PositiveInteger
  unitPrice: Money
}
~~~

### 23.4. Pricing function

~~~text
function calculateSubtotal(order: Order): Money {
  return order.items.sum(
    item => item.unitPrice * item.quantity
  )
}
~~~

### 23.5. Validation rules

~~~text
rule orderHasItems {
  require order.items.count() > 0
}

rule orderTotalIsValid {
  require order.total == calculateSubtotal(order)
}
~~~

### 23.6. Workflow

~~~text
workflow orderFulfillment(order: Order) {
  initial state SUBMITTED

  transition SUBMITTED -> VALIDATED
    on validationPassed

  transition VALIDATED -> RESERVED
    on inventoryReserved

  transition RESERVED -> PAYMENT_PENDING
    on paymentRequested

  transition PAYMENT_PENDING -> PAID
    on payment.accepted

  transition PAID -> SHIPPED
    on shipment.dispatched
}
~~~

### 23.7. Host capability

DSL được cấp:
- ReadOrderCapability.
- ReserveInventoryCapability.
- RequestPaymentCapability.
- DispatchShipmentCapability.

Không có raw database hoặc arbitrary network API.

### 23.8. Compiler pipeline

Source được parse, resolve symbol, type-check, validate state transition, lower thành IR và package thành workflow artifact.

### 23.9. Runtime

Runtime nhận event, load instance, evaluate guard, gọi action qua capability, persist state và phát telemetry.

### 23.10. Tooling

Domain expert dùng editor có completion, diagnostics và preview. Developer dùng CLI và CI để validate, test và package.

### 23.11. Testing

Test pricing function, validation rule, state transition, duplicate event, payment timeout, inventory failure và tenant isolation.

### 23.12. Release

Artifact ghi language version, compiler version, schema version và capability requirement. Triển khai staging, kiểm tra telemetry rồi rollout production.

### 23.13. Evolution

Khi Order bổ sung currency và shipping address, tạo schema version mới, migration plan và compatibility window. Workflow instance cũ tiếp tục theo definition đã pin hoặc migrate theo checkpoint.

## 24. Các deliverable nên có sau mỗi giai đoạn

| Giai đoạn | Deliverable |
| --- | --- |
| Discovery | Problem statement, persona, success metrics |
| Domain analysis | Glossary, domain model, workflow map |
| Scope | Use case, non-goals, trust boundary |
| Language design | Vocabulary, syntax proposal, semantics |
| Type design | Type catalog, null and numeric rules |
| Compiler design | Grammar, AST, IR, pipeline architecture |
| Runtime design | Execution model, host API, persistence |
| Security | Threat model, capability model, sandbox policy |
| Tooling | CLI, IDE integration, formatter, debugger |
| Testing | Parser, semantic, integration, performance, security suites |
| Documentation | Tutorial, reference, examples, migration guide |
| Release | Artifact manifest, release notes, deployment plan |
| Governance | Ownership, proposal process, compatibility policy |

Deliverable giúp nhóm biết quyết định nào đã được chốt và phần nào còn cần thử nghiệm.

## 25. Lộ trình triển khai theo từng mức trưởng thành

Không cần triển khai mọi thành phần cùng lúc. Có thể phát triển theo các mức.

### 25.1. Prototype

- Một use case.
- Vocabulary nhỏ.
- Parser đơn giản.
- Type checking cơ bản.
- Interpreter.
- Bộ ví dụ chạy được.

Mục tiêu là kiểm tra DSL có giải quyết vấn đề tốt hơn cách hiện tại không.

### 25.2. MVP

- Grammar và semantics được tài liệu hóa.
- Diagnostics ổn định.
- CLI.
- Test suite.
- Host API giới hạn.
- Version cơ bản.
- Một integration thật.

### 25.3. Production-ready

- Security model.
- Resource limit.
- Runtime recovery.
- Observability.
- Artifact provenance.
- Compatibility policy.
- Documentation và support process.
- CI/CD integration.

### 25.4. Mature platform

- Incremental compilation.
- IDE và debugger hoàn chỉnh.
- Plugin ecosystem.
- Nhiều backend.
- Schema migration tooling.
- Performance regression tracking.
- Governance và release cadence.

### 25.5. Đánh giá trước khi mở rộng

Chỉ thêm capability khi có nhu cầu và có owner. Mỗi feature mới làm tăng grammar, semantics, testing và maintenance surface.

## 26. Những sai lầm thường gặp trong toàn bộ quy trình

**Bắt đầu bằng cú pháp.** Syntax được thiết kế trước domain có thể phản ánh suy nghĩ của developer thay vì người dùng. Hãy khảo sát nghiệp vụ trước.

**Phạm vi quá rộng.** Cố xây general-purpose language làm tăng complexity. Hãy chọn một vertical slice có giá trị.

**Không đặc tả semantics.** Cú pháp có thể parse nhưng behavior không rõ. Hãy định nghĩa evaluation, type, error và effect.

**Dùng type quá yếu.** Nhiều field String làm mất domain meaning và tăng runtime validation. Hãy tạo domain type phù hợp.

**Không có diagnostics tốt.** Người dùng biết chương trình lỗi nhưng không biết sửa ở đâu. Hãy giữ source mapping và diagnostic code.

**Trộn domain với framework.** Domain logic phụ thuộc trực tiếp API của một tool. Hãy tạo boundary có giá trị.

**Bỏ qua security.** DSL do người dùng cung cấp có thể truy cập tài nguyên ngoài dự kiến. Hãy xây threat model và capability từ đầu.

**Không kiểm thử migration.** Schema và workflow dài hạn có thể không tương thích. Hãy version và test instance cũ.

**Không đo hiệu năng.** Tối ưu dựa trên cảm giác có thể làm hệ thống phức tạp hơn. Hãy benchmark và profile workload đại diện.

**Thiếu tooling.** Ngôn ngữ có semantics tốt nhưng không có formatter, completion hoặc debugger khó sử dụng. Hãy xem tooling là một phần của sản phẩm.

**Không có ownership.** Không ai chịu trách nhiệm language evolution hoặc runtime support. Hãy xác định owner và governance.

## 27. Kết luận

Quy trình thiết kế hoàn chỉnh đưa DSL từ một vấn đề nghiệp vụ cụ thể đến một ngôn ngữ có thể sử dụng, triển khai và tiến hóa. Công việc bắt đầu bằng discovery và domain modeling, tiếp tục qua scope, vocabulary, type system, syntax, grammar và semantics, rồi đến parser, AST, compiler hoặc interpreter, runtime, host integration, security, tooling, testing, documentation, release và governance.

Một DSL tốt cần cân bằng khả năng biểu đạt với độ đơn giản, tính linh hoạt với an toàn, portability với hiệu năng và tốc độ phát triển với chi phí bảo trì. Các quyết định quan trọng phải có contract và được kiểm chứng bằng ví dụ, test, benchmark và trải nghiệm người dùng. Versioning, migration, observability và ownership giúp ngôn ngữ tiếp tục hoạt động khi dữ liệu, hệ thống và nhu cầu thay đổi.

Hãy bắt đầu từ một use case có giá trị, xây một vertical slice hoàn chỉnh và kiểm chứng nó với người dùng thật. Sau đó mở rộng từng lớp dựa trên bằng chứng, giữ semantics nhất quán và quản lý dependency có chủ đích. Khi ngôn ngữ, compiler, runtime và công cụ được thiết kế như một sản phẩm thống nhất, DSL có thể trở thành một phần bền vững của kiến trúc phần mềm.

